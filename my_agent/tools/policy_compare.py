"""
Policy comparison tools — connects to hip-backend to fetch real
policy limits, calculate live premiums, and generate a comparison PDF.
"""
import os
import logging
import requests
from typing import Optional
import google.genai.types as types
from google.adk.tools import ToolContext

_BACKEND = os.getenv("BACKEND_BASE_URL", "http://localhost:5000")
_JWT = os.getenv("AGENT_JWT_TOKEN", "")

# Logs go to stdout (visible in your terminal where you run `python main.py`)
# and also to a file: hip/policy_compare.log
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "..", "policy_compare.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("policy_compare")


def _auth_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Cookie": f"Authorization={_JWT}",
    }


def search_policies(query: str) -> dict:
    """
    Searches health insurance policies by name using the backend search API.
    Use this to resolve a policy name to its policy_id, limits_id, and subplans
    before calling calculate_premium or generate_policy_comparison_pdf.

    Always call this first when the user mentions a policy by name.

    Args:
        query: Policy or company name (e.g. "Star", "HDFC Ergo").

    Returns:
        dict with matching policies, each containing:
          - policy_id, limits_id, name, company, subplans [{subplan_id, name}]
    """
    try:
        log.info("search_policies | query=%r | url=%s/policy", query, _BACKEND)
        res = requests.get(
            f"{_BACKEND}/policy",
            params={"search": query, "limit": 5},
            headers=_auth_headers(),
            timeout=10,
        )
        log.info("search_policies | status=%d", res.status_code)
        if res.status_code != 200:
            log.error("search_policies | error body: %s", res.text[:300])
            return {"status": "error", "message": f"hip-backend returned {res.status_code}"}

        data = res.json()
        policies = data.get("data", []) if isinstance(data, dict) else data
        log.info("search_policies | total results from API: %d", len(policies))

        if not policies:
            log.warning("search_policies | no matches for query=%r", query)
            return {"status": "not_found", "message": f"No policies matched '{query}'."}

        results = []
        for p in policies[:3]:
            company_raw = p.get("companyId") or {}
            subpolicies = p.get("subPolicies") or []
            subplans = []
            for s in subpolicies:
                sub_limits = s.get("limits") or []
                limits_id = sub_limits[0].get("_id") if sub_limits else None
                subplans.append({
                    "subplan_id": s.get("_id"),
                    "name": s.get("name", ""),
                    "limits_id": limits_id,
                })

            results.append({
                "policy_id": p.get("_id"),
                "name": p.get("name"),
                "company": company_raw.get("name", "") if isinstance(company_raw, dict) else "",
                "subplans": subplans,
            })

        log.info("search_policies | returning %d match(es): %s",
                 len(results), [r["name"] for r in results])
        return {"status": "success", "matches": results}

    except Exception as e:
        log.exception("search_policies | exception: %s", e)
        return {"status": "error", "message": str(e)}


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
    and member configuration. Returns the premium amount and the premiumBody
    needed for generate_policy_comparison_pdf.

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
        dict with 'premium_body' ready for the comparison tool, plus the final premium amount.
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
        log.info("calculate_premium | policy=%s subplan=%s limit=%s age=%s adults=%d",
                 policy_id, subplan_id, sum_insured, age, adults)
        res = requests.post(
            f"{_BACKEND}/premiumCalculator/calculate",
            json=body,
            headers=_auth_headers(),
            timeout=10,
        )
        log.info("calculate_premium | status=%d", res.status_code)
        if res.status_code != 200:
            log.error("calculate_premium | error body: %s", res.text[:300])
            return {"status": "error", "message": f"hip-backend returned {res.status_code}: {res.text[:200]}"}

        data = res.json()
        log.debug("calculate_premium | full response: %s", data)
        inner = data.get("data", {}) if isinstance(data, dict) else {}
        log.debug("calculate_premium | inner keys: %s", list(inner.keys()) if isinstance(inner, dict) else inner)
        amount = inner.get("totalRateAmountWithGst") or inner.get("totalRateAmount") or 0
        log.info("calculate_premium | amount=%s", amount)

        return {
            "status": "success",
            "premium_body": body,
            "amount": amount,
        }
    except Exception as e:
        log.exception("calculate_premium | exception: %s", e)
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
        log.info("generate_comparison_pdf | limits=[%s, %s] amounts=[%s, %s]",
                 limits_id_1, limits_id_2, amount_1, amount_2)
        res = requests.post(
            f"{_BACKEND}/limit/pdf_compare_premium_new_html",
            json=payload,
            headers=_auth_headers(),
            timeout=30,
        )
        log.info("generate_comparison_pdf | html fetch status=%d", res.status_code)
        if res.status_code != 200:
            log.error("generate_comparison_pdf | error body: %s", res.text[:300])
            return {
                "status": "error",
                "message": f"hip-backend returned {res.status_code}: {res.text[:200]}",
            }
        html_content = res.text
        log.info("generate_comparison_pdf | html length=%d chars | preview: %s",
                 len(html_content), html_content[:200])

    except Exception as e:
        log.exception("generate_comparison_pdf | html fetch exception: %s", e)
        return {"status": "error", "message": f"Failed to fetch comparison HTML: {e}"}

    # Convert HTML → PDF (WeasyPrint requires GTK libs — available on Linux/EC2)
    # Falls back to saving raw HTML if running on Windows without GTK
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html_content, base_url=_BACKEND).write_pdf()
        mime_type = "application/pdf"
        filename_ext = "pdf"
        log.info("generate_comparison_pdf | pdf size=%d bytes", len(pdf_bytes))
    except Exception as e:
        log.warning("generate_comparison_pdf | weasyprint unavailable (%s) — saving as HTML instead", e)
        pdf_bytes = html_content.encode("utf-8")
        mime_type = "text/html"
        filename_ext = "html"

    # Save as artifact — identical pattern to generate_insurance_summary_pdf
    artifact = types.Part.from_bytes(data=pdf_bytes, mime_type=mime_type)
    p1_name = (premium_body_1.get("policy") or "policy1")[-6:]
    p2_name = (premium_body_2.get("policy") or "policy2")[-6:]
    filename = f"comparison_{p1_name}_vs_{p2_name}.{filename_ext}"

    try:
        version = await tool_context.save_artifact(filename=filename, artifact=artifact)
    except Exception as e:
        return {"status": "error", "message": f"Failed to save artifact: {e}"}

    return {
        "status": "success",
        "filename": filename,
        "version": version,
        "instruction": "Tell the user their policy comparison is ready and attached — they can download it now.",
    }
