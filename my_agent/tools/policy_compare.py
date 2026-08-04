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

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
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
    Tries progressively shorter search terms if the full query returns nothing.

    Args:
        query: Policy or company name (e.g. "Star", "HDFC Ergo").

    Returns:
        dict with matching policies, each containing:
          - policy_id, name, company, subplans [{subplan_id, name, limits_id}]
    """
    # Build a list of search terms to try: full query first, then each word
    terms = [query.strip()]
    for word in query.strip().split():
        if word not in terms and len(word) > 3:
            terms.append(word)

    for term in terms:
        try:
            res = requests.get(
                f"{_BACKEND}/policy",
                params={"search": term, "limit": 5},
                headers=_auth_headers(),
                timeout=10,
            )
            if res.status_code != 200:
                log.error("search_policies FAILED | status=%d | body=%s", res.status_code, res.text[:200])
                return {"status": "error", "message": f"hip-backend returned {res.status_code}"}

            data = res.json()
            policies = data.get("data", []) if isinstance(data, dict) else data

            if not policies:
                log.warning("search_policies NO RESULTS | query=%r", term)
                continue

            results = []
            for p in policies[:3]:
                company_raw = p.get("companyId") or {}
                subpolicies = p.get("subPolicies") or []
                
                # Skip policies with no subpolicies — can't calculate premium for them
                if not subpolicies:
                    log.warning("search_policies SKIP | policy=%s | reason=no subPolicies", p.get("name"))
                    continue
                
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

            if not results:
                log.warning("search_policies NO USABLE RESULTS | query=%r | all policies had no subPolicies", term)
                continue

            log.info("search_policies OK | term=%r | matches=%s", term, [r["name"] for r in results])
            return {"status": "success", "matches": results}

        except Exception as e:
            log.exception("search_policies EXCEPTION | %s", e)
            return {"status": "error", "message": str(e)}

    log.warning("search_policies NOT FOUND | all terms exhausted for query=%r", query)
    return {
        "status": "not_found",
        "message": f"No policy matching '{query}' found in our system. Tell the user this policy is not available and ask if they want to try a different one.",
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
    and member configuration. Returns the premium amount and the premiumBody
    needed for generate_policy_comparison_pdf.

    Args:
        policy_id:    MongoDB ObjectID of the policy.
        subplan_id:   MongoDB ObjectID of the subplan.
        sum_insured:  Coverage amount in INR (e.g. 500000 for 5 lakh).
        period:       Policy period in years as string: "1", "2", or "3" (tool auto-converts to "1 Year" etc.).
        adults:       Number of adults to cover.
        children:     Number of children to cover.
        age:          Age of the oldest adult as string (e.g. "35").
        gender:       "male" or "female".
        zone:         Geographic zone string if applicable (optional).

    Returns:
        dict with 'premium_body' ready for the comparison tool, plus the final premium amount.
    """
    # Backend expects "1 Year", "2 Years", "3 Years" format, not just "1", "2", "3"
    period_map = {
        "1": "1 Year",
        "2": "2 Years",
        "3": "3 Years",
        "4": "4 Years",
        "5": "5 Years",
    }
    formatted_period = period_map.get(period.strip(), period)  # fallback to original if already formatted
    
    body = {
        "policy": policy_id,
        "subplan": subplan_id,
        "limit": sum_insured,
        "period": formatted_period,
        "adult": adults,
        "child": children,
        "age": age,
        "gender": gender,
        "insured": [],  # Required by backend — members array (empty = use adult/child/age/gender)
    }
    if zone:
        body["zone"] = zone

    try:
        log.info("calculate_premium REQUEST | body=%s", body)
        res = requests.post(
            f"{_BACKEND}/premiumCalculator/calculate",
            json=body,
            headers=_auth_headers(),
            timeout=10,
        )
        if res.status_code != 200:
            log.error("calculate_premium FAILED | status=%d | body=%s", res.status_code, res.text[:200])
            return {"status": "error", "message": f"hip-backend returned {res.status_code}: {res.text[:200]}"}

        data = res.json()
        log.info("calculate_premium RESPONSE | %s", data)

        # API returns errors as HTTP 200 with code:400 in body
        body_code = data.get("code") if isinstance(data, dict) else None
        if body_code and body_code != 200:
            msg = data.get("msg") or data.get("message") or "Premium not available"
            log.error("calculate_premium BODY ERROR | code=%s | msg=%s", body_code, msg)
            return {"status": "error", "message": msg}

        inner = data.get("data", {}) if isinstance(data, dict) else {}
        amount = inner.get("totalRateAmountWithGst") or inner.get("totalRateAmount") or 0
        log.info("calculate_premium OK | policy=%s | amount=%s", policy_id, amount)

        return {
            "status": "success",
            "premium_body": body,
            "amount": amount,
        }
    except Exception as e:
        log.exception("calculate_premium EXCEPTION | %s", e)
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
    limits = [limits_id_1, limits_id_2]
    type_map = {1: "single", 2: "double"}
    comparison_type = type_map.get(len(limits), "multiple")

    # Step 1: Fetch the full limit document object for limits_id_1
    # Backend requires the full object in "limit", not just the ID string
    try:
        log.info("generate_comparison_pdf FETCHING limit object | id=%s", limits_id_1)
        limit_res = requests.get(
            f"{_BACKEND}/limit/{limits_id_1}",
            headers=_auth_headers(),
            timeout=10,
        )
        if limit_res.status_code != 200:
            log.error("generate_comparison_pdf LIMIT FETCH FAILED | status=%d | body=%s", limit_res.status_code, limit_res.text[:200])
            return {"status": "error", "message": f"Failed to fetch limit document: {limit_res.status_code}"}
        limit_object = limit_res.json().get("data", {})
        log.info("generate_comparison_pdf LIMIT OBJECT OK | keys=%s", list(limit_object.keys()) if isinstance(limit_object, dict) else "non-dict")
    except Exception as e:
        log.exception("generate_comparison_pdf LIMIT FETCH EXCEPTION | %s", e)
        return {"status": "error", "message": f"Failed to fetch limit document: {e}"}

    # Step 2: Build payload with full limit object
    payload = {
        "type": comparison_type,
        "limit": limit_object,  # full document object, NOT just the ID string
        "limits": limits,
        "actualPeriod": premium_body_1.get("period", "1 Year"),
        "amount": [amount_1, amount_2],
        "bank": [
            "000000000000000000000000000000",
            "000000000000000000000000000000",
        ],
        "premiumBody": premium_body_1,
        "premiumBody2": premium_body_2,
    }

    try:
        log.info("generate_comparison_pdf CALLING HTML endpoint | type=%s | limits=%s", comparison_type, limits)
        res = requests.post(
            f"{_BACKEND}/limit/pdf_compare_premium_new_html",
            json=payload,
            headers=_auth_headers(),
            timeout=30,
        )
        if res.status_code != 200:
            log.error("generate_comparison_pdf HTML FAILED | status=%d | body=%s", res.status_code, res.text[:300])
            return {
                "status": "error",
                "message": f"hip-backend returned {res.status_code}: {res.text[:200]}",
            }

        html_content = res.text
        log.info("generate_comparison_pdf HTML RESPONSE | length=%d | preview=%s", len(html_content), html_content[:200])

        # Detect JSON error body (backend returns {"code":400,"msg":"..."} with HTTP 200)
        if html_content.strip().startswith("{") and len(html_content) < 500:
            try:
                import json as _json
                err = _json.loads(html_content)
                msg = err.get("msg") or err.get("message") or "error occurred while printing pdf"
                log.error("generate_comparison_pdf BACKEND ERROR IN BODY | %s", msg)
                return {"status": "error", "message": f"Comparison PDF failed: {msg}"}
            except Exception:
                pass  # not JSON, proceed normally

    except Exception as e:
        log.exception("generate_comparison_pdf HTML EXCEPTION | %s", e)
        return {"status": "error", "message": f"Failed to fetch comparison HTML: {e}"}

    try:
        from weasyprint import HTML as WeasyprintHTML
        pdf_bytes = WeasyprintHTML(string=html_content, base_url=_BACKEND).write_pdf()
        log.info("generate_comparison_pdf PDF OK | size=%d bytes", len(pdf_bytes))
    except Exception as e:
        log.exception("generate_comparison_pdf WEASYPRINT FAILED | %s", e)
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
    }
