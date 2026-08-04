"""
Policy comparison tools — connects to hip-backend to fetch real
policy limits, calculate live premiums, and generate a comparison PDF.
"""
import os
import requests
from typing import Optional
import google.genai.types as types
from google.adk.tools import ToolContext

_BACKEND = os.getenv("BACKEND_BASE_URL", "http://localhost:5000")
_JWT = os.getenv("AGENT_JWT_TOKEN", "")


def _auth_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Cookie": f"Authorization={_JWT}",
    }


def get_policy_limits(policy_id: str) -> dict:
    """
    Fetches the limits document for a given policy ID from hip-backend.
    Returns the limits document ID needed for comparison and PDF generation.
    Call this for each policy before generating a comparison.

    Args:
        policy_id: The MongoDB ObjectID string of the policy.

    Returns:
        dict with 'limits_id' (the _id of the limits document) or an error.
    """
    try:
        res = requests.get(
            f"{_BACKEND}/limit/{policy_id}",
            headers=_auth_headers(),
            timeout=10,
        )
        if res.status_code != 200:
            return {"status": "error", "message": f"hip-backend returned {res.status_code}: {res.text[:200]}"}
        data = res.json()
        return {
            "status": "success",
            "limits_id": data.get("_id"),
            "policy_id": policy_id,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def calculate_premium(
    policy_id: str,
    subplan_id: str,
    sum_insured: int,
    period: str,
    adults: int,
    children: int,
    age: str,
    gender: str,
    zone: Optional[str] = None,
) -> dict:
    """
    Calculates a live premium quote from hip-backend for a specific policy
    and member configuration. Returns the full premiumBody needed for comparison.

    Args:
        policy_id:    MongoDB ObjectID of the policy.
        subplan_id:   MongoDB ObjectID of the subplan.
        sum_insured:  Coverage amount in INR (e.g. 500000 for 5 lakh).
        period:       Policy period in years as string: "1", "2", or "3".
        adults:       Number of adults to cover.
        children:     Number of children to cover.
        age:          Age of the oldest adult as string (e.g. "35").
        gender:       "male" or "female".
        zone:         Geographic zone string if applicable (optional).

    Returns:
        dict with 'premium_body' ready for the comparison tool, plus calculated amounts.
    """
    body = {
        "policy": policy_id,
        "subplan": subplan_id,
        "limit": sum_insured,
        "period": period,
        "adult": adults,
        "child": children,
        "age": age,
        "gender": gender,
    }
    if zone:
        body["zone"] = zone

    try:
        res = requests.post(
            f"{_BACKEND}/premiumCalculator/calculate",
            json=body,
            headers=_auth_headers(),
            timeout=10,
        )
        if res.status_code != 200:
            return {"status": "error", "message": f"hip-backend returned {res.status_code}: {res.text[:200]}"}
        data = res.json()
        return {
            "status": "success",
            "premium_body": body,
            "quote": data,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def generate_policy_comparison_pdf(
    limits_id_1: str,
    premium_body_1: dict,
    limits_id_2: str,
    premium_body_2: dict,
    tool_context: ToolContext,
    amount_1: int = 0,
    amount_2: int = 0,
) -> dict:
    """
    Generates a side-by-side policy comparison PDF using hip-backend's
    HTML comparison engine. Saves the result as an artifact — same as other
    PDF guides in this chat. Use this after getting limits IDs and premiumBodies
    from get_policy_limits and calculate_premium.

    Args:
        limits_id_1:    Limits document _id for the first policy.
        premium_body_1: premiumBody dict from calculate_premium for policy 1.
        limits_id_2:    Limits document _id for the second policy.
        premium_body_2: premiumBody dict from calculate_premium for policy 2.
        tool_context:   ADK tool context for saving the artifact.
        amount_1:       Calculated premium amount for policy 1 (optional, 0 if unknown).
        amount_2:       Calculated premium amount for policy 2 (optional, 0 if unknown).

    Returns:
        dict with status, filename, and instructions for the agent.
    """
    payload = {
        "type": "multiple",
        "limits": [limits_id_1, limits_id_2],
        "actualPeriod": premium_body_1.get("period", "1"),
        "amount": [amount_1, amount_2],
        "bank": [
            "000000000000000000000000000000",
            "000000000000000000000000000000",
        ],
        "premiumBody": premium_body_1,
        "premiumBody2": premium_body_2,
    }

    try:
        res = requests.post(
            f"{_BACKEND}/limit/pdf_compare_premium_new_html",
            json=payload,
            headers=_auth_headers(),
            timeout=30,
        )
        if res.status_code != 200:
            return {
                "status": "error",
                "message": f"hip-backend returned {res.status_code}: {res.text[:200]}",
            }

        html_content = res.text

    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch comparison HTML: {e}"}

    # Convert HTML → PDF
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content, base_url=_BACKEND).write_pdf()
    except Exception as e:
        return {"status": "error", "message": f"PDF conversion failed: {e}"}

    # Save as artifact — identical pattern to generate_insurance_summary_pdf
    artifact = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    p1_name = (premium_body_1.get("policy") or "policy1")[-6:]
    p2_name = (premium_body_2.get("policy") or "policy2")[-6:]
    filename = f"comparison_{p1_name}_vs_{p2_name}.pdf"

    try:
        version = await tool_context.save_artifact(filename=filename, artifact=artifact)
    except Exception as e:
        return {"status": "error", "message": f"Failed to save artifact: {e}"}

    return {
        "status": "success",
        "filename": filename,
        "version": version,
        "size_bytes": len(pdf_bytes),
        "instruction": "Tell the user their policy comparison is ready and attached — they can download it now.",
    }
