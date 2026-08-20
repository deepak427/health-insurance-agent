"""
Addon tools — browse available addons and apply them to a booking.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from typing import Optional
from google.adk.tools import ToolContext
from data.store import load
from data.bookings import get_booking, update_booking


def get_available_addons(category: str = "") -> dict:
    """
    Returns available insurance add-on options that can be added to a travel policy.
    Call this when a user asks about addons, extra coverage, enhancements, or says
    things like 'are there any addons', 'I'm a smoker', 'do you cover adventure sports',
    'any health upgrades', etc.

    Args:
        category (str): Optional filter keyword — e.g. 'health', 'smoker', 'sports',
                        'baggage', 'covid', 'car', 'maternity', 'cancellation'.
                        If empty, returns all addons.

    Returns:
        dict: Available addons with pricing and highlights.
    """
    addons_catalog: dict = load("addons")

    if not addons_catalog:
        return {"status": "error", "message": "No addons configured."}

    cat_lower = category.lower().strip()
    if cat_lower:
        filtered = {
            k: v for k, v in addons_catalog.items()
            if cat_lower in " ".join(v.get("categories", [])).lower()
            or cat_lower in v.get("name", "").lower()
            or cat_lower in v.get("description", "").lower()
        }
        result = filtered if filtered else addons_catalog  # fall back to all if no match
    else:
        result = addons_catalog

    return {
        "status": "success",
        "addons": result,
        "instruction": (
            "Present these as ADDON_CARDS so the user can pick interactively. "
            "Show a short intro line like 'Here are the available add-ons:' then embed the ADDON_CARDS block."
        ),
    }


async def apply_addon_to_booking(
    ref_number: str,
    addon_keys: list,
    tool_context: ToolContext,
) -> dict:
    """
    Adds selected addons to an existing booking and recalculates the total premium.
    Call this after the user has chosen one or more addons and confirmed they want to add them.

    Args:
        ref_number (str): Booking reference number (e.g. "BUD-A3F7K").
        addon_keys (list): List of addon keys from the catalog
                           (e.g. ["health_cover_upgrade", "smoker_cover"]).
        tool_context:      ADK tool context.

    Returns:
        dict with updated booking summary including new premium.
    """
    booking = get_booking(ref_number)
    if not booking:
        return {
            "status": "not_found",
            "message": f"No booking found for reference {ref_number.upper()}.",
        }

    cfg = load("addons")
    addons_catalog: dict = cfg if isinstance(cfg, dict) else {}

    # Validate addon keys
    invalid = [k for k in addon_keys if k not in addons_catalog]
    if invalid:
        return {
            "status": "error",
            "message": f"Unknown addon key(s): {invalid}. Valid keys: {list(addons_catalog.keys())}",
        }

    num_adults = booking.get("num_adults", 1) or 1
    num_children = booking.get("num_children", 0) or 0
    total_people = num_adults + num_children

    # Calculate addon cost
    addon_cost = 0
    addon_details = []
    for key in addon_keys:
        addon = addons_catalog[key]
        if "price_per_person" in addon:
            cost = addon["price_per_person"] * total_people
        else:
            cost = addon.get("price_flat", 0)
        addon_cost += cost
        addon_details.append({
            "key": key,
            "name": addon["name"],
            "cost": cost,
        })

    # Merge with existing addons (avoid duplicates)
    existing_addons = booking.get("addons") or []
    if isinstance(existing_addons, str):
        import json
        existing_addons = json.loads(existing_addons) if existing_addons else []
    merged_addons = list({a if isinstance(a, str) else a.get("key", ""): a for a in (
        [{"key": k} for k in existing_addons if isinstance(k, str)] + addon_details
    )}.values())

    # Recalculate premium
    try:
        base_premium = float(str(booking.get("premium", "0")).replace("₹", "").replace(",", "").strip())
    except ValueError:
        base_premium = 0

    new_premium = base_premium + addon_cost
    new_premium_str = f"{new_premium:,.0f}"

    # Persist
    success = update_booking(
        ref_number,
        addons=merged_addons,
        premium=new_premium_str,
        notes=(booking.get("notes") or "") + f"\nAddons added: {[d['name'] for d in addon_details]}",
    )

    if not success:
        return {"status": "error", "message": "Failed to update booking."}

    return {
        "status": "success",
        "ref_number": ref_number.upper(),
        "addons_added": addon_details,
        "addon_cost": addon_cost,
        "previous_premium": f"{base_premium:,.0f}",
        "new_premium": new_premium_str,
        "instruction": (
            "Tell the user their addons have been applied, show the updated premium clearly, "
            "and offer to regenerate the booking confirmation PDF with the addons included."
        ),
    }
