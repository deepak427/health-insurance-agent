import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from data.store import load


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
    faq_data = load("faqs")
    topic_lower = topic.lower().strip()

    if topic_lower in faq_data:
        return {"status": "found", "topic": topic_lower, "info": faq_data[topic_lower]}

    for key in faq_data:
        if topic_lower in key or key in topic_lower:
            return {"status": "found", "topic": key, "info": faq_data[key]}

    return {
        "status": "not_found",
        "message": f"No FAQ for '{topic}'.",
        "available_topics": list(faq_data.keys()),
    }
