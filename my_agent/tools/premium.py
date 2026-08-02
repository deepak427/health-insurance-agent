import sys, os
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from data.store import load


def estimate_premium(
    insurance_type: str,
    age: int,
    coverage_amount: float,
    additional_info: Optional[str] = None,
) -> dict:
    """
    Provides a rough premium estimate for insurance coverage.

    Args:
        insurance_type (str): Type of insurance: 'life', 'health', 'auto', 'home'.
        age (int): Age of the primary insured person.
        coverage_amount (float): Desired coverage amount in USD.
        additional_info (str, optional): Extra context like 'smoker', 'family plan', 'luxury car'.

    Returns:
        dict: Estimated premium range and factors affecting the price.
    """
    cfg = load("premium_config")
    disclaimer = cfg.get("disclaimer", "")
    t = insurance_type.lower()
    extra = (additional_info or "").lower()

    if t == "life":
        c = cfg["life"]
        rate = c["rate_under_40"] if age < 40 else (c["rate_40_to_55"] if age < 55 else c["rate_over_55"])
        if "smoker" in extra:
            rate *= c["smoker_multiplier"]
        annual = coverage_amount * rate
        return {
            "type": "Term Life Insurance",
            "estimated_monthly": round(annual / 12, 2),
            "estimated_annual": round(annual, 2),
            "factors": c["factors"],
            "disclaimer": disclaimer,
        }

    if t == "health":
        c = cfg["health"]
        monthly = c["monthly_under_30"] if age < 30 else (c["monthly_30_to_50"] if age < 50 else c["monthly_over_50"])
        if "family" in extra:
            monthly *= c["family_multiplier"]
        return {
            "type": "Health Insurance",
            "estimated_monthly": round(monthly, 2),
            "note": c.get("note", ""),
            "factors": c["factors"],
            "disclaimer": disclaimer,
        }

    if t == "auto":
        c = cfg["auto"]
        annual = c["annual_base_25_plus"] if age >= 25 else c["annual_base_under_25"]
        if "luxury" in extra:
            annual *= c["luxury_multiplier"]
        return {
            "type": "Auto Insurance",
            "estimated_annual": round(annual, 2),
            "estimated_monthly": round(annual / 12, 2),
            "factors": c["factors"],
            "disclaimer": disclaimer,
        }

    if t == "home":
        c = cfg["home"]
        annual = coverage_amount * c["rate_of_coverage"]
        return {
            "type": "Home Insurance",
            "estimated_annual": round(annual, 2),
            "estimated_monthly": round(annual / 12, 2),
            "factors": c["factors"],
            "disclaimer": disclaimer,
        }

    return {
        "status": "error",
        "message": f"Unknown type '{insurance_type}'. Supported: life, health, auto, home.",
    }
