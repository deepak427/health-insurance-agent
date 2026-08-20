"""
Booking management tools — save, retrieve, and update bookings by reference number.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from google.adk.tools import ToolContext
from data.bookings import create_booking, get_booking, update_booking


async def save_booking(
    policy_name: str,
    insurer: str,
    destination: str,
    travel_dates: str,
    num_adults: int,
    num_children: int,
    traveller_ages: str,
    sum_insured: str,
    premium: str,
    tool_context: ToolContext,
    notes: str = "",
    addons: list = None,
) -> dict:
    """
    Saves a confirmed booking to the database and returns a reference number.
    Call this AFTER the booking is confirmed and AFTER generate_booking_confirmation_pdf.
    Pass the confirmation PDF filename as part of notes if available.

    The reference number (e.g. BUD-A3F7K) should be shared with the user
    so they can look up this booking later from any conversation.

    Args:
        policy_name:     Name of the booked policy.
        insurer:         Insurer/company name.
        destination:     Travel destination.
        travel_dates:    Travel dates string.
        num_adults:      Number of adult travellers.
        num_children:    Number of child travellers.
        traveller_ages:  Ages as a string.
        sum_insured:     Coverage amount.
        premium:         Premium paid.
        tool_context:    ADK tool context (provides user_id and session_id).
        notes:           Any extra notes (e.g. confirmation PDF filename).
        addons:          List of addon keys already selected (if any).

    Returns:
        dict with ref_number.
    """
    user_id = tool_context.user_id if hasattr(tool_context, "user_id") else ""
    session_id = tool_context.session_id if hasattr(tool_context, "session_id") else ""

    # Collect artifact filenames from this session if possible
    artifact_ids = []
    try:
        listed = await tool_context.list_artifacts()
        artifact_ids = listed if isinstance(listed, list) else []
    except Exception:
        pass

    ref = create_booking(
        user_id=user_id,
        session_id=session_id,
        policy_name=policy_name,
        insurer=insurer,
        destination=destination,
        travel_dates=travel_dates,
        num_adults=num_adults,
        num_children=num_children,
        traveller_ages=traveller_ages,
        sum_insured=sum_insured,
        premium=premium,
        artifact_ids=artifact_ids,
        addons=addons or [],
        notes=notes,
    )
    return {"status": "success", "ref_number": ref}


async def get_booking_details(
    ref_number: str,
    tool_context: ToolContext,
) -> dict:
    """
    Retrieves booking details for a given reference number.
    Use this when a user mentions their booking reference or asks about a past booking.

    Args:
        ref_number:   The booking reference (e.g. "BUD-A3F7K"). Case-insensitive.
        tool_context: ADK tool context.

    Returns:
        dict with full booking details, or status "not_found".
    """
    booking = get_booking(ref_number)
    if not booking:
        return {
            "status": "not_found",
            "message": f"No booking found for reference {ref_number.upper()}. Please double-check the reference number.",
        }
    return {"status": "success", "booking": booking}


async def update_booking_details(
    ref_number: str,
    tool_context: ToolContext,
    status: str = "",
    notes: str = "",
    travel_dates: str = "",
    destination: str = "",
    premium: str = "",
    addons: list = None,
) -> dict:
    """
    Updates an existing booking record (e.g. status change, add notes, update dates, update addons/premium).
    Use this when the user wants to modify or annotate a booked policy.

    Args:
        ref_number:   The booking reference (e.g. "BUD-A3F7K").
        tool_context: ADK tool context.
        status:       New status — e.g. "confirmed", "cancelled", "docs_received".
        notes:        Notes to append or set.
        travel_dates: Updated travel dates if changed.
        destination:  Updated destination if changed.
        premium:      Updated premium if addons changed the total.
        addons:       Updated list of addon objects/keys if addons were added/removed.

    Returns:
        dict with status.
    """
    fields = {}
    if status:
        fields["status"] = status
    if notes:
        fields["notes"] = notes
    if travel_dates:
        fields["travel_dates"] = travel_dates
    if destination:
        fields["destination"] = destination
    if premium:
        fields["premium"] = premium
    if addons is not None:
        fields["addons"] = addons

    updated = update_booking(ref_number, **fields)
    if not updated:
        return {
            "status": "not_found",
            "message": f"No booking found for reference {ref_number.upper()}.",
        }
    return {"status": "success", "ref_number": ref_number.upper()}
