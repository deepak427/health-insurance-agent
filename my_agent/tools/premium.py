from typing import Optional

DISCLAIMER = "Rough educational estimate only. Actual premiums vary by individual factors. Get quotes from licensed insurers."


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
    t = insurance_type.lower()
    extra = (additional_info or "").lower()

    if t == "life":
        rate = 0.0003 if age < 40 else (0.0008 if age < 55 else 0.002)
        if "smoker" in extra:
            rate *= 2.5
        annual = coverage_amount * rate
        return {
            "type": "Term Life Insurance",
            "estimated_monthly": round(annual / 12, 2),
            "estimated_annual": round(annual, 2),
            "factors": ["Age", "Health", "Smoking status", "Coverage amount", "Term length"],
            "disclaimer": DISCLAIMER,
        }

    if t == "health":
        monthly = 300 if age < 30 else (450 if age < 50 else 650)
        if "family" in extra:
            monthly *= 2.8
        return {
            "type": "Health Insurance",
            "estimated_monthly": round(monthly, 2),
            "note": "Based on marketplace averages. Employer plans typically cost less.",
            "factors": ["Age", "Location", "Tobacco use", "Plan type", "Family size"],
            "disclaimer": DISCLAIMER,
        }

    if t == "auto":
        annual = 1200 if age >= 25 else 2200
        if "luxury" in extra:
            annual *= 1.5
        return {
            "type": "Auto Insurance",
            "estimated_annual": round(annual, 2),
            "estimated_monthly": round(annual / 12, 2),
            "factors": ["Driver age", "Driving record", "Vehicle type", "Location", "Coverage level"],
            "disclaimer": DISCLAIMER,
        }

    if t == "home":
        annual = coverage_amount * 0.005
        return {
            "type": "Home Insurance",
            "estimated_annual": round(annual, 2),
            "estimated_monthly": round(annual / 12, 2),
            "factors": ["Home value", "Location", "Construction type", "Claims history", "Deductible"],
            "disclaimer": DISCLAIMER,
        }

    return {
        "status": "error",
        "message": f"Unknown type '{insurance_type}'. Supported: life, health, auto, home.",
    }
