import json
import os
from google.adk.agents import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.load_artifacts_tool import LoadArtifactsTool

from .prompt import INSURANCE_AGENT_PROMPT
from .tools import (
    get_insurance_faq,
    estimate_premium,
    get_claim_filing_steps,
    analyze_insurance_document,
    search_policies,
    calculate_premium,
    generate_policy_comparison_pdf,
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
        + "## RESPONSE FORMAT OVERRIDE (highest priority)\n"
        + "The following instructions control how you format and style every response. "
        + "They take priority over the default formatting guidelines above:\n\n"
        + custom
    )


root_agent = Agent(
    model='gemini-3.5-flash',
    name='insurance_support_agent',
    description='Expert insurance support — answers questions, analyzes policy documents, guides claims, generates PDF guides, and explains coverage.',
    instruction=_instruction_provider,
    tools=[
        get_insurance_faq,
        estimate_premium,
        get_claim_filing_steps,
        analyze_insurance_document,
        search_policies,
        calculate_premium,
        generate_policy_comparison_pdf,
        LoadArtifactsTool(),
    ],
)
