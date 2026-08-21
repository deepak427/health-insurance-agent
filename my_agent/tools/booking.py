"""
Booking management tools — save, retrieve, and update bookings by reference number.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from google.adk.tools import ToolContext
from data.bookings import create_booking, get_booking, update_booking, get_recent_bookings as _get_recent_bookings
from data.wallet import get_wallet, deduct_wallet_credits, parse_amount


async def get_my_wallet_balance(tool_context: ToolContext) -> dict:
    """
    Checks the current agent/user's available wallet credits balance.
    Use this when the user asks about their credit balance or wallet funds.

    Args:
        tool_context: ADK tool context.

    Returns:
        dict with available credit balance.
    """
    user_id = tool_context.user_id if hasattr(tool_context, "user_id") else ""
    wallet = get_wallet(user_id)
    return {
        "status": "success",
        "user_id": wallet["user_id"],
        "available_credits": wallet["balance"],
        "message": f"Your current wallet balance is ₹{wallet['balance']:,.0f} credits.",
    }


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
    status: str = "complete",
    agent_commission: str = "",
) -> dict:
    """
    Saves a completed policy booking to the database and deducts the required premium credits from user wallet.
    Only call this when ALL details (trip details + traveler KYC details/documents for every traveler) are collected.
    Returns a reference number on success.

    If wallet credits are insufficient to cover the premium, NO booking is created and an
    'insufficient_credits' status is returned.

    Args:
        policy_name:      Name of the booked policy.
        insurer:          Insurer/company name.
        destination:      Travel destination.
        travel_dates:     Travel dates string.
        num_adults:       Number of adult travellers.
        num_children:     Number of child travellers.
        traveller_ages:   Ages as a string.
        sum_insured:      Coverage amount.
        premium:          Actual insurer premium to deduct in credits (e.g. '₹1,200').
        tool_context:     ADK tool context (provides user_id and session_id).
        notes:            Traveler names, DOBs, KYC details, or extra notes.
        addons:           List of addon keys already selected (if any).
        status:           Booking status: 'complete' (default).
        agent_commission: Agent commission / markup amount (e.g. '₹500'). Auto-calculated at 40% if not given.

    Returns:
        dict with ref_number, status, and remaining_credits, or insufficient_credits error.
    """
    user_id = tool_context.user_id if hasattr(tool_context, "user_id") else ""
    session_id = tool_context.session_id if hasattr(tool_context, "session_id") else ""

    premium_num = parse_amount(premium)
    if premium_num > 0:
        success, wallet = deduct_wallet_credits(user_id, premium_num)
        if not success:
            return {
                "status": "insufficient_credits",
                "message": f"Cannot complete booking: Insufficient wallet credits. Required: ₹{premium_num:,.0f}, Available: ₹{wallet['balance']:,.0f}. Please top up your wallet credits to proceed.",
                "available_credits": wallet["balance"],
                "required_credits": premium_num,
            }
    else:
        wallet = get_wallet(user_id)

    # Collect artifact filenames from this session if possible
    artifact_ids = []
    try:
        listed = await tool_context.list_artifacts()
        artifact_ids = listed if isinstance(listed, list) else []
    except Exception:
        pass

    if not agent_commission and premium_num > 0:
        agent_commission = f"₹{round(premium_num * 0.40):,.0f}"

    booking_status = status or "complete"

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
        status=booking_status,
        agent_commission=agent_commission or "",
    )
    return {
        "status": "success",
        "ref_number": ref,
        "booking_status": booking_status,
        "remaining_credits": wallet["balance"],
        "deducted_credits": premium_num,
        "agent_commission": agent_commission,
    }


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


async def get_recent_bookings(
    tool_context: ToolContext,
    limit: int = 4,
) -> dict:
    """
    Returns the most recent bookings for the current user (up to `limit`).
    Use this when the user asks to see their recent bookings, booking history,
    or past policies — even without a specific reference number.

    Args:
        tool_context: ADK tool context (provides user_id).
        limit:        Max number of bookings to return (default 4, max 20).

    Returns:
        dict with "bookings" list and "count".
    """
    user_id = tool_context.user_id if hasattr(tool_context, "user_id") else ""
    limit = min(max(1, limit), 20)
    bookings = _get_recent_bookings(user_id, limit)
    return {"status": "success", "bookings": bookings, "count": len(bookings)}


async def update_booking_details(
    ref_number: str,
    tool_context: ToolContext,
    status: str = "",
    notes: str = "",
    travel_dates: str = "",
    destination: str = "",
    premium: str = "",
    addons: list = None,
    agent_commission: str = "",
) -> dict:
    """
    Updates an existing booking record (e.g. status change, add notes, update dates, update addons/premium).
    Also automatically syncs any new artifacts (uploaded documents) from the current session into the booking.
    Use this when the user wants to modify or annotate a booked policy.

    Args:
        ref_number:        The booking reference (e.g. "BUD-A3F7K").
        tool_context:      ADK tool context.
        status:            New status — e.g. "confirmed", "cancelled", "docs_received".
        notes:             Notes to append or set.
        travel_dates:      Updated travel dates if changed.
        destination:       Updated destination if changed.
        premium:           Updated premium if addons changed the total.
        addons:            Updated list of addon objects/keys if addons were added/removed.
        agent_commission:  Updated agent commission amount.

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
    if agent_commission:
        fields["agent_commission"] = agent_commission

    # Always sync the full artifact list from this session into the booking
    try:
        listed = await tool_context.list_artifacts()
        if listed and isinstance(listed, list):
            # Merge with existing artifact_ids to avoid duplicates
            existing = get_booking(ref_number)
            existing_ids = set(existing.get("artifact_ids", []) if existing else [])
            merged = list(existing_ids | set(listed))
            fields["artifact_ids"] = merged
    except Exception:
        pass

    updated = update_booking(ref_number, **fields)
    if not updated:
        return {
            "status": "not_found",
            "message": f"No booking found for reference {ref_number.upper()}.",
        }
    return {"status": "success", "ref_number": ref_number.upper()}
