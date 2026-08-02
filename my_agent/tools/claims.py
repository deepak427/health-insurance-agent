CLAIM_GUIDES = {
    "auto accident": {
        "immediate_steps": [
            "Ensure safety and call 911 if needed",
            "Exchange info: name, contact, license plate, insurance details",
            "Take photos of damage and the scene",
            "Get a police report number",
        ],
        "filing_steps": [
            "Contact your insurer within 24–48 hours",
            "Provide: date/time/location, accident description, other party info",
            "Schedule vehicle inspection with adjuster",
            "Get repair estimates from approved shops",
        ],
        "documents_needed": ["Police report", "Photos/videos", "Other driver's info", "Medical records if injured"],
        "timeline": "Most claims resolved in 1–4 weeks",
    },
    "health": {
        "steps": [
            "Receive medical service",
            "Provider submits claim to insurer (usually automatic)",
            "Insurer sends Explanation of Benefits (EOB)",
            "Pay your portion (copay/coinsurance/deductible)",
            "Appeal if denied",
        ],
        "if_denied": [
            "Request written explanation",
            "Gather supporting medical records",
            "File internal appeal",
            "Request external review if internal appeal fails",
        ],
        "documents_needed": ["EOB from insurer", "Medical bills", "Doctor's notes"],
    },
    "home damage": {
        "immediate_steps": [
            "Ensure family safety first",
            "Make temporary repairs to prevent further damage",
            "Document all damage with photos/video before cleanup",
            "Save all receipts for emergency expenses",
        ],
        "filing_steps": [
            "Call insurer as soon as possible",
            "Get a claim number",
            "Meet with adjuster for inspection",
            "Get independent contractor estimates",
        ],
        "documents_needed": ["Photos/videos", "Itemized damage list", "Contractor estimates"],
        "tip": "Keep a home inventory — it speeds up claims significantly.",
    },
    "life insurance": {
        "steps": [
            "Notify the insurance company of the death",
            "Request and complete claim forms",
            "Submit certified death certificate",
            "Provide original policy documents",
            "Choose payout method (lump sum or installments)",
        ],
        "documents_needed": ["Certified death certificate", "Original policy", "Claimant ID"],
        "timeline": "Most claims paid within 30–60 days of complete documentation",
    },
    "theft": {
        "immediate_steps": [
            "File a police report immediately",
            "Document all stolen/damaged items",
        ],
        "filing_steps": [
            "Contact insurer promptly with police report number",
            "Submit itemized list of stolen property with values",
            "Provide proof of ownership if available",
        ],
        "documents_needed": ["Police report", "Itemized loss list", "Receipts/serial numbers if available"],
    },
    "natural disaster": {
        "immediate_steps": [
            "Prioritize safety — evacuate if necessary",
            "Document damage before any cleanup",
            "Make temporary repairs, keep all receipts",
        ],
        "note": "Standard home insurance covers wind/hail/fire but NOT floods or earthquakes — those need separate policies.",
        "filing_steps": [
            "Contact insurer once safe",
            "Document all damage thoroughly",
            "Check if FEMA disaster assistance applies",
        ],
    },
}


def get_claim_filing_steps(claim_type: str) -> dict:
    """
    Returns step-by-step guidance for filing an insurance claim.

    Args:
        claim_type (str): Type of claim. E.g. 'auto accident', 'health',
                          'home damage', 'life insurance', 'theft', 'natural disaster'.

    Returns:
        dict: Step-by-step guide and required documents for the claim.
    """
    claim_lower = claim_type.lower().strip()

    for key in CLAIM_GUIDES:
        if claim_lower in key or key in claim_lower:
            return {"status": "found", "claim_type": key, "guide": CLAIM_GUIDES[key]}

    return {
        "status": "not_found",
        "message": f"No specific guide for '{claim_type}'.",
        "available_types": list(CLAIM_GUIDES.keys()),
        "general_advice": "Contact your insurer directly, document everything, and file promptly.",
    }
