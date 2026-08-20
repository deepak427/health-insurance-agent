"""
VAS (Value-Added Services) tools — browse and apply agency-bundled services.
VAS are services offered by the agency itself (Doctor on Call, Air Ambulance, etc.)
and are separate from insurer add-ons.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from google.adk.tools import ToolContext
from data.store import load
from data.bookings import get_booking, update_booking


def get_available_vas(category: str = "") -> dict:
    """
    Returns available Value-Added Services (VAS) offered by the agency — things like
    Doctor on Call, Air Ambulance, Travel Concierge, Emergency Cash, etc.
    These are agency-provided services, NOT insurer add-ons.

    Call this when the user asks about VAS, value-added services, extra services,
    or mentions specific services like 'doctor on call', 'air ambulance', 'concierge',
    'lounge access', 'emergency cash', etc.

    Args:
        category (str): Optional filter — e.g. 'medical', 'travel', 'emergency',
                        'financial', 'comfort'. If empty, returns all VAS.

    Returns:
        dict: Available VAS with pricing and highlights.
    """
    vas_catalog: dict = load("vas")

    if not vas_catalog:
        return {"status": "error", "message": "No VAS configured."}

    cat_lower = category.lower().strip()
    if cat_lower:
        filtered = {
            k: v for k, v in vas_catalog.items()
            if cat_lower in " ".join(v.get("categories", [])).lower()
            or cat_lower in v.get("name", "").lower()
            or cat_lower in v.get("description", "").lower()
        }
        result = filtered if filtered else vas_catalog
    else:
        result = vas_catalog

    return {
        "status": "success",
        "vas": result,
        "instruction": (
            "Present these as VAS_CARDS so the user can pick interactively. "
            "Clarify these are agency-provided services, not insurer add-ons. "
            "Show a short intro line then embed the VAS_CARDS block."
        ),
    }


async def apply_vas_to_booking(
    ref_number: str,
    vas_keys: list,
    tool_context: ToolContext,
) -> dict:
    """
    Applies selected VAS (Value-Added Services) to an existing booking and
    recalculates the total premium/price.

    Args:
        ref_number (str): Booking reference (e.g. "BUD-A3F7K").
        vas_keys (list):  List of VAS keys to add (e.g. ["doctor_on_call", "air_ambulance"]).
        tool_context:     ADK tool context.

    Returns:
        dict with updated booking summary including new total.
    """
    booking = get_booking(ref_number)
    if not booking:
        return {
            "status": "not_found",
            "message": f"No booking found for reference {ref_number.upper()}.",
        }

    vas_catalog: dict = load("vas")

    invalid = [k for k in vas_keys if k not in vas_catalog]
    if invalid:
        return {
            "status": "error",
            "message": f"Unknown VAS key(s): {invalid}. Valid keys: {list(vas_catalog.keys())}",
        }

    num_adults = booking.get("num_adults", 1) or 1
    num_children = booking.get("num_children", 0) or 0
    total_people = num_adults + num_children

    vas_cost = 0
    vas_details = []
    for key in vas_keys:
        svc = vas_catalog[key]
        if "price_per_person" in svc:
            cost = svc["price_per_person"] * total_people
        else:
            cost = svc.get("price_flat", 0)
        vas_cost += cost
        vas_details.append({"key": key, "name": svc["name"], "cost": cost})

    # Merge VAS with existing addons in booking
    existing_addons = booking.get("addons") or []
    if isinstance(existing_addons, str):
        import json
        try:
            existing_addons = json.loads(existing_addons) if existing_addons else []
        except Exception:
            existing_addons = []

    addons_map = {}
    for item in existing_addons:
        if isinstance(item, dict):
            k = item.get("key") or item.get("name") or str(item)
            addons_map[k] = item
        elif isinstance(item, str):
            addons_map[item] = {"key": item, "name": item, "cost": 0}

    for d in vas_details:
        addons_map[d["key"]] = {"key": d["key"], "name": f"[VAS] {d['name']}", "cost": d["cost"]}

    merged_addons = list(addons_map.values())

    vas_names = [d["name"] for d in vas_details]
    existing_notes = booking.get("notes") or ""

    try:
        base_premium = float(
            str(booking.get("premium", "0")).replace("₹", "").replace(",", "").strip()
        )
    except ValueError:
        base_premium = 0

    new_premium = base_premium + vas_cost
    new_premium_str = f"{new_premium:,.0f}"

    success = update_booking(
        ref_number,
        addons=merged_addons,
        premium=new_premium_str,
        notes=existing_notes + f"\nVAS added: {vas_names}",
    )

    if not success:
        return {"status": "error", "message": "Failed to update booking."}

    return {
        "status": "success",
        "ref_number": ref_number.upper(),
        "vas_added": vas_details,
        "all_addons": merged_addons,
        "vas_cost": vas_cost,
        "previous_premium": f"{base_premium:,.0f}",
        "new_total": new_premium_str,
        "instruction": (
            "Tell the user their VAS services have been added, show the updated total clearly, "
            "and offer to regenerate the booking confirmation PDF with all addons and VAS included."
        ),
    }
