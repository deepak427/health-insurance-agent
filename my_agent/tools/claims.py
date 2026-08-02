import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from data.store import load


def get_claim_filing_steps(claim_type: str) -> dict:
    """
    Returns step-by-step guidance for filing an insurance claim.

    Args:
        claim_type (str): Type of claim. E.g. 'auto accident', 'health',
                          'home damage', 'life insurance', 'theft', 'natural disaster'.

    Returns:
        dict: Step-by-step guide and required documents for the claim.
    """
    claim_guides = load("claims")
    claim_lower = claim_type.lower().strip()

    for key in claim_guides:
        if claim_lower in key or key in claim_lower:
            return {"status": "found", "claim_type": key, "guide": claim_guides[key]}

    return {
        "status": "not_found",
        "message": f"No specific guide for '{claim_type}'.",
        "available_types": list(claim_guides.keys()),
        "general_advice": "Contact your insurer directly, document everything, and file promptly.",
    }
