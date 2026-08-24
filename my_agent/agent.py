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

_OFF_TOPIC_INSTRUCTION = (
    "STRICT SCOPE RULE: You are ONLY allowed to help with travel insurance topics — "
    "quotes, premiums, bookings, claims, policy documents, addons, VAS, and wallet/credits. "
    "If the user asks about ANYTHING else (coding, writing, jokes, recipes, general knowledge, "
    "weather, stocks, or any non-insurance topic), respond with exactly: "
    "'I can only help with travel insurance. What can I assist you with?' "
    "Do NOT answer the off-topic question under any circumstances."
)

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
    """Block prompt injections. Inject off-topic scope rule into every system instruction."""
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

    # 1. Prompt injection / secret fishing — fast deterministic check
    if any(pattern in lower for pattern in _BLOCKED):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Sorry, I can't help with that.")],
            )
        )

    # 2. Inject the off-topic scope rule into the system instruction on every request.
    #    The LLM enforces it — no extra API call needed.
    if llm_request.config is None:
        from google.genai import types as _types
        llm_request.config = _types.GenerateContentConfig()

    existing = llm_request.config.system_instruction
    if existing and hasattr(existing, "parts") and existing.parts:
        # Append to existing system instruction
        existing.parts[0].text = (existing.parts[0].text or "") + "\n\n" + _OFF_TOPIC_INSTRUCTION
    else:
        llm_request.config.system_instruction = types.Content(
            role="system",
            parts=[types.Part(text=_OFF_TOPIC_INSTRUCTION)],
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
    model='gemini-3.5-flash',
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
