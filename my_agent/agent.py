from google.adk.agents import Agent
from google.adk.tools.load_artifacts_tool import LoadArtifactsTool

from .prompt import INSURANCE_AGENT_PROMPT
from .tools import (
    get_insurance_faq,
    estimate_premium,
    get_claim_filing_steps,
    analyze_insurance_document,
    generate_insurance_summary_pdf,
)

root_agent = Agent(
    model='gemini-2.5-flash-latest',
    name='insurance_support_agent',
    description='Expert insurance support — answers questions, analyzes policy documents, guides claims, generates PDF guides, and explains coverage.',
    instruction=INSURANCE_AGENT_PROMPT,
    tools=[
        get_insurance_faq,
        estimate_premium,
        get_claim_filing_steps,
        analyze_insurance_document,
        generate_insurance_summary_pdf,
        LoadArtifactsTool(),
    ],
)
