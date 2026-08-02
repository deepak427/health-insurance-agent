FAQ_DATA = {
    "deductible": {
        "definition": "The amount you pay out-of-pocket before your insurance starts covering costs.",
        "example": "If your deductible is $1,000 and you have a $3,000 claim, you pay $1,000 and insurance covers $2,000.",
        "tip": "Higher deductibles usually mean lower monthly premiums.",
    },
    "premium": {
        "definition": "The regular payment you make to keep your insurance policy active (monthly, quarterly, or annually).",
        "example": "Paying $200/month for health insurance is your premium.",
        "tip": "Premiums vary based on age, health, coverage amount, and risk factors.",
    },
    "copay": {
        "definition": "A fixed amount you pay for a specific healthcare service, separate from your deductible.",
        "example": "$20 copay for a doctor visit means you pay $20 regardless of the total bill.",
        "tip": "Copays don't usually count toward your deductible.",
    },
    "claim": {
        "definition": "A formal request to your insurance company to cover a loss or event under your policy.",
        "steps": [
            "1. Document the incident (photos, police reports, medical records)",
            "2. Notify your insurer promptly",
            "3. Fill out the claim form",
            "4. Submit supporting documents",
            "5. Work with the assigned adjuster",
            "6. Receive settlement or decision",
        ],
        "tip": "File claims promptly — most policies have time limits.",
    },
    "exclusion": {
        "definition": "Events or conditions specifically NOT covered by your insurance policy.",
        "examples": ["Pre-existing conditions (some health plans)", "Flood damage (standard home insurance)", "Wear and tear (auto)"],
        "tip": "You can often buy riders or endorsements to add coverage for exclusions.",
    },
    "beneficiary": {
        "definition": "The person(s) designated to receive the payout when a claim is made.",
        "tip": "Keep beneficiary designations updated after major life events.",
    },
    "life insurance": {
        "types": {
            "term life": "Covers you for a specific period (10–30 years). More affordable.",
            "whole life": "Permanent coverage with a cash value component.",
            "universal life": "Flexible permanent coverage with investment options.",
        },
        "tip": "Common rule of thumb: coverage = 10–12x your annual income.",
    },
    "health insurance": {
        "key_terms": ["Premium", "Deductible", "Copay", "Coinsurance", "Out-of-pocket maximum", "Network"],
        "types": ["HMO", "PPO", "EPO", "HDHP"],
        "tip": "Always check if your doctors are in-network before enrolling.",
    },
    "auto insurance": {
        "types": {
            "liability": "Covers damage/injury you cause to others. Usually legally required.",
            "collision": "Covers your car in an accident regardless of fault.",
            "comprehensive": "Covers non-collision damage (theft, weather, animals).",
            "uninsured motorist": "Protects you if hit by an uninsured driver.",
        },
        "tip": "Full coverage = liability + collision + comprehensive.",
    },
    "home insurance": {
        "covers": ["Dwelling structure", "Personal property", "Liability", "Additional living expenses"],
        "does_not_cover": ["Floods", "Earthquakes", "Normal wear and tear"],
        "tip": "Usually required by mortgage lenders.",
    },
}


def get_insurance_faq(topic: str) -> dict:
    """
    Returns FAQ information about an insurance topic.

    Args:
        topic (str): Insurance topic to look up. E.g. 'deductible', 'premium',
                     'copay', 'claim', 'exclusion', 'life insurance',
                     'health insurance', 'auto insurance', 'home insurance'.

    Returns:
        dict: FAQ content for the topic.
    """
    topic_lower = topic.lower().strip()

    if topic_lower in FAQ_DATA:
        return {"status": "found", "topic": topic_lower, "info": FAQ_DATA[topic_lower]}

    for key in FAQ_DATA:
        if topic_lower in key or key in topic_lower:
            return {"status": "found", "topic": key, "info": FAQ_DATA[key]}

    return {
        "status": "not_found",
        "message": f"No FAQ for '{topic}'.",
        "available_topics": list(FAQ_DATA.keys()),
    }
