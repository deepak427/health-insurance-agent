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

# Token usage tracking — path relative to agent file
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from data.token_usage import record_usage

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
    """Block prompt injections only. Off-topic rule is enforced via the system prompt."""
    last_msg = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == "user" and content.parts:
                last_msg = " ".join(
                    p.text for p in content.parts if hasattr(p, "text") and p.text
                )
                break

    lower = last_msg.lower()

    if any(pattern in lower for pattern in _BLOCKED):
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="Sorry, I can't help with that.")],
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


# ── Token usage tracker ───────────────────────────────────────────────────────
def _after_model_token_tracker(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Record token usage after every LLM call without modifying the response."""
    try:
        usage = getattr(llm_response, "usage_metadata", None)
        print(f"[token_tracker] fired — usage_metadata={usage}")

        if not usage:
            # Some ADK versions wrap it differently — try the raw response
            raw = getattr(llm_response, "raw", None) or getattr(llm_response, "_raw_response", None)
            if raw:
                usage = getattr(raw, "usage_metadata", None)
            print(f"[token_tracker] fallback raw usage={usage}")

        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        print(f"[token_tracker] prompt={prompt_tokens} output={output_tokens}")

        user_id = (
            callback_context.state.get("user_id")
            or callback_context.state.get("userId")
            or "unknown"
        )
        session_id = (
            callback_context.state.get("session_id")
            or callback_context.state.get("sessionId")
            or "unknown"
        )
        print(f"[token_tracker] user_id={user_id} session_id={session_id}")

        record_usage(
            user_id=str(user_id),
            session_id=str(session_id),
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )
        print(f"[token_tracker] recorded OK")
    except Exception as e:
        import traceback
        print(f"[token_tracker] ERROR: {e}")
        traceback.print_exc()
    return None  # never modify the response


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
    after_model_callback=_after_model_token_tracker,
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
