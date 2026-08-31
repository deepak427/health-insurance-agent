import json
import os
from typing import Any, Dict, Optional
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.agents.context_cache_config import ContextCacheConfig

# Hard cap on the number of content entries (not turns) sent to the model.
# Each user turn with tool calls generates ~4-6 content entries.
# 20 entries ≈ 3-4 meaningful back-and-forth turns including tool calls.
# Lower = cheaper. Raise if the agent forgets context too quickly.
_MAX_HISTORY_ENTRIES = 20

# Token usage tracking
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
# NOTE: "token" removed — it's a common word users legitimately use
_BLOCKED = [
    ".env", "api_key", "apikey", "secret", "password", "passwd",
    "ignore previous", "ignore all", "disregard", "forget instructions",
    "system prompt", "credentials", "private key", "access key",
]


# Tools that mutate bookings or wallet — must have a matching user_id in session state
_PROTECTED_TOOLS = {
    "save_booking",
    "apply_addon_to_booking",
    "apply_vas_to_booking",
    "update_booking_details",
}


# ── Guardrail 1: screen user input + strip images + limit history ─────────────
def _before_model_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """
    1. Block prompt injections (unchanged).
    2. Strip inline image/binary data from ALL history messages so the raw
       passport photo (or any other uploaded file) is not re-sent to the model
       on every subsequent turn — this is the #1 cause of the 600k+ token bills.
    3. Truncate history to the last _MAX_HISTORY_TURNS user+model turn pairs
       so that long sessions don't keep growing the context window indefinitely.
    """
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

    # ── Strip inline binary data from ALL contents (images, PDFs, etc.) ───────
    # LoadArtifactsTool (now removed) used to inject PDF blobs into every turn.
    # Belt-and-suspenders: strip any inline_data that sneaks in from any source.
    # Documents are processed by extract_traveler_details_from_document /
    # analyze_insurance_document via their own genai.Client calls — the model
    # never needs the raw bytes in the conversation context.
    if llm_request.contents:
        for content in llm_request.contents:
            if not content.parts:
                continue
            stripped = []
            for part in content.parts:
                if hasattr(part, "inline_data") and part.inline_data is not None:
                    mime = getattr(part.inline_data, "mime_type", "file") or "file"
                    stripped.append(types.Part(text=f"[uploaded {mime} — already processed]"))
                else:
                    stripped.append(part)
            content.parts = stripped

    # ── Limit history to the last N content entries to cap prompt size ──────
    # ADK stores each tool call and tool response as a separate content entry.
    # A single agent turn with 2 tool calls = 5 entries:
    #   [user_msg, tool_call_1, tool_resp_1, tool_call_2, tool_resp_2, model_reply]
    # So capping by "turns" vastly underestimates the real entry count.
    # We cap by raw entry count instead — always keep the last entry (current msg).
    if llm_request.contents and len(llm_request.contents) > _MAX_HISTORY_ENTRIES:
        llm_request.contents = llm_request.contents[-_MAX_HISTORY_ENTRIES:]

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
        if not usage:
            return None

        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        # Try session state first, fall back to ContextVars set by middleware
        user_id = (
            callback_context.state.get("user_id")
            or callback_context.state.get("userId")
        )
        session_id = (
            callback_context.state.get("session_id")
            or callback_context.state.get("sessionId")
        )

        # Fall back to ContextVars injected by the HTTP middleware
        if not user_id or not session_id:
            try:
                from main import _current_user_id, _current_session_id
                user_id = user_id or _current_user_id.get("unknown")
                session_id = session_id or _current_session_id.get("unknown")
            except ImportError:
                pass

        user_id = str(user_id or "unknown")
        session_id = str(session_id or "unknown")

        print(f"[token_tracker] prompt={prompt_tokens} output={output_tokens} user={user_id} session={session_id}")

        record_usage(
            user_id=user_id,
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        import traceback
        print(f"[token_tracker] ERROR: {e}")
        traceback.print_exc()
    return None


def _build_instruction() -> str:
    """Build the full system instruction, merging in any custom response style."""
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
    # Use static_instruction so ADK caches it server-side instead of re-sending
    # the full prompt on every tool-call round-trip within a single user turn.
    # A dynamic `instruction=callable` is re-evaluated on every LLM call —
    # with 2 tool calls per turn that's 3x the prompt tokens wasted.
    instruction=_build_instruction(),
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
    ],
)

app = App(
    name="insurance_support_agent_app",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        token_threshold=4000,
        event_retention_size=2
    ),
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,
        ttl_seconds=600,
        cache_intervals=5
    )
)
