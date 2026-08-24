import json
import os
from typing import Any, Dict, Optional
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.load_artifacts_tool import LoadArtifactsTool
from google.genai import types

from .prompt import INSURANCE_AGENT_PROMPT
from .tools import (
    get_insurance_faq,
    estimate_premium,
    get_claim_filing_steps,
    analyze_insurance_document,
    extract_traveler_details_from_document,
    generate_booking_confirmation_pdf,
    generate_quotation_comparison_pdf,
    save_booking,
    get_booking_details,
    get_recent_bookings,
    update_booking_details,
    get_my_wallet_balance,
    get_available_addons,
    apply_addon_to_booking,
    get_available_vas,
    apply_vas_to_booking,
)

_RESPONSE_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "response_prompt.json",
)

# Patterns that indicate prompt injection / fishing for secrets
_BLOCKED = [
    ".env", "api_key", "apikey", "secret", "password", "passwd",
    "ignore previous", "ignore all", "disregard", "forget instructions",
    "system prompt", "token", "credentials", "private key", "access key",
]

_CLASSIFIER_PROMPT = """You are a strict topic classifier for a travel insurance assistant.

Determine if the user's message is related to ANY of these topics:
- Travel insurance (quotes, premiums, policies, coverage)
- Booking or managing a travel insurance policy
- Claims filing or policy documents
- Addons or value-added services for insurance
- Wallet/credits for insurance bookings
- General greetings or small talk (hi, hello, thanks, bye)

Reply with ONLY one word: YES if it is related, NO if it is not.

User message: {message}"""


def _classify_message(message: str) -> bool:
    """Returns True if on-topic, False if off-topic.
    Fails open (returns True) on any error so valid users are never blocked."""
    try:
        from google import genai as google_genai
        import os
        api_key = os.environ.get("GEMINI_API_KEY")
        client = google_genai.Client(api_key=api_key) if api_key else google_genai.Client()
        response = client.models.generate_content(
            model="gemini-3.7-flash",
            contents=_CLASSIFIER_PROMPT.format(message=message),
            config={"temperature": 0, "max_output_tokens": 5},
        )
        answer = response.text.strip().upper()
        return not answer.startswith("NO")
    except Exception:
        return True  # fail open — don't block on classifier errors

# Tools that mutate bookings or wallet — must have a matching user_id in session state
_PROTECTED_TOOLS = {
    "save_booking",
    "apply_addon_to_booking",
    "apply_vas_to_booking",
    "update_booking_details",
}


# ── Guardrail 1: screen user input before it reaches the LLM ──────────────────
def _before_model_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Block prompt injections and off-topic requests via LLM classifier."""
    # Extract the last user message text
    last_msg = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == "user" and content.parts:
                last_msg = " ".join(
                    p.text for p in content.parts if hasattr(p, "text") and p.text
                )
                break

    lower = last_msg.lower()

    # 1. Prompt injection / secret fishing — fast keyword check (keep this, it's cheap & deterministic)
    if any(pattern in lower for pattern in _BLOCKED):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Sorry, I can't help with that.")],
            )
        )

    # 2. Off-topic check via LLM classifier — handles any language, any phrasing
    if last_msg and not _classify_message(last_msg):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(
                    text="I'm only set up to help with travel insurance — "
                         "quotes, bookings, claims, addons, and policy questions. "
                         "What can I help you with?"
                )],
            )
        )

    return None  # allow the request through


# ── Guardrail 2: validate user_id before mutating tools execute ───────────────
def _before_tool_guardrail(
    tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext
) -> Optional[Dict]:
    """Ensure mutating tool calls are only made for the session's own user."""
    if tool.name not in _PROTECTED_TOOLS:
        return None  # not a protected tool — allow

    session_user_id = tool_context.state.get("user_id") or tool_context.state.get("userId")
    arg_user_id = args.get("user_id") or args.get("userId")

    # If the session carries a user_id, the tool arg must match it
    if session_user_id and arg_user_id and session_user_id != arg_user_id:
        return {
            "status": "error",
            "message": "Unauthorized: user mismatch. Action blocked.",
        }

    return None  # allow


def _load_response_prompt() -> str:
    """Load and sanitize the user-defined response prompt from disk."""
    try:
        with open(_RESPONSE_PROMPT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        text = str(data.get("prompt", "")).strip()
        if not text:
            return ""
        lower = text.lower()
        if any(blocked in lower for blocked in _BLOCKED):
            return ""  # silently ignore — fall back to default formatting
        # Cap length so no one buries a huge prompt injection
        return text[:1000]
    except Exception:
        return ""


def _instruction_provider(context: ReadonlyContext) -> str:
    custom = _load_response_prompt()
    if not custom:
        return INSURANCE_AGENT_PROMPT
    return (
        INSURANCE_AGENT_PROMPT
        + "\n\n---\n"
        + "## USER CUSTOM RESPONSE STYLE & TONE\n"
        + "The following instructions customize your tone, phrasing, and visual styling. "
        + "Note: They do NOT override core business workflows, tool calling logic, KYC document requirements, or PDF generation rules defined above:\n\n"
        + custom
    )


root_agent = Agent(
    model='gemini-3.7-flash',
    name='insurance_support_agent',
    description='Expert insurance support for agents — answers questions, analyzes policy documents, guides claims, manages bookings, and generates booking confirmations.',
    instruction=_instruction_provider,
    before_model_callback=_before_model_guardrail,
    before_tool_callback=_before_tool_guardrail,
    tools=[
        get_insurance_faq,
        estimate_premium,
        get_claim_filing_steps,
        analyze_insurance_document,
        extract_traveler_details_from_document,
        generate_booking_confirmation_pdf,
        generate_quotation_comparison_pdf,
        save_booking,
        get_booking_details,
        get_recent_bookings,
        update_booking_details,
        get_my_wallet_balance,
        get_available_addons,
        apply_addon_to_booking,
        get_available_vas,
        apply_vas_to_booking,
        LoadArtifactsTool(),
    ],
)
