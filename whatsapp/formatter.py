"""
WhatsApp formatter with Interactive Message support.

Takes the agent's raw response string (which may contain embedded card markers
like <!--POLICY_CARDS:[...]-->) and produces either:
  1. WhatsApp Interactive List/Button messages (native rich UI)
  2. Clean, readable plain text fallback

WhatsApp Interactive Message Types:
  - Interactive List: Up to 10 items with title + description (for policies, addons, VAS)
  - Interactive Buttons: Up to 3 buttons (for confirmations, quick actions)
  - Plain text: Fallback for older WhatsApp versions

Card types handled:
  POLICY_CARDS        → Interactive List with policy options
  ADDON_CARDS         → Interactive List with addon options
  VAS_CARDS           → Interactive List with VAS options
  BOOKING_CARDS       → Plain text booking summary
  BOOKING_TABLE       → Plain text booking list
  CONFIRM_BOOKING     → Interactive Buttons (Confirm/Modify/Cancel)
  Any unknown card    → stripped silently (never crashes)

PDF artifacts are NOT handled here — they are sent as WhatsApp document
messages by the webhook handler after it collects artifact filenames.
"""
import json
import re
from typing import Optional, Dict, List, Union


# Regex that matches ANY card comment block, e.g.:
#   <!--POLICY_CARDS:[{...}]-->
_CARD_RE = re.compile(
    r"<!--\s*([A-Z_]+)\s*:\s*(\[.*?\]|\{.*?\})\s*-->",
    re.DOTALL,
)


def _fmt_policy_cards(cards: list) -> str:
    lines = ["*Policy Options:*\n"]
    for i, c in enumerate(cards, 1):
        name = c.get("name") or c.get("plan_name") or "Plan"
        insurer = c.get("insurer") or c.get("provider") or ""
        premium = c.get("premium") or c.get("price") or ""
        cover = c.get("sum_insured") or c.get("coverage") or c.get("cover") or ""
        features = c.get("features") or c.get("highlights") or []

        line = f"{i}. *{name}*"
        if insurer:
            line += f" — {insurer}"
        if premium:
            line += f"\n   Premium: {premium}"
        if cover:
            line += f" | Cover: {cover}"
        if features and isinstance(features, list):
            line += "\n   " + " • ".join(str(f) for f in features[:3])
        lines.append(line)
    lines.append("\nReply with the number to select a plan.")
    return "\n".join(lines)


def _fmt_addon_cards(cards: list) -> str:
    lines = ["*Available Add-ons:*\n"]
    for c in cards:
        name = c.get("name") or c.get("title") or "Addon"
        price = c.get("price") or c.get("premium") or ""
        desc = c.get("description") or c.get("desc") or ""
        line = f"• *{name}*"
        if price:
            line += f" — {price}"
        if desc:
            line += f"\n  {desc}"
        lines.append(line)
    lines.append("\nReply with the add-on name to apply it.")
    return "\n".join(lines)


def _fmt_vas_cards(cards: list) -> str:
    lines = ["*Value Added Services:*\n"]
    for c in cards:
        name = c.get("name") or c.get("title") or "Service"
        price = c.get("price") or c.get("cost") or ""
        desc = c.get("description") or c.get("desc") or ""
        line = f"• *{name}*"
        if price:
            line += f" — {price}"
        if desc:
            line += f"\n  {desc}"
        lines.append(line)
    lines.append("\nReply with the service name to add it.")
    return "\n".join(lines)


def _fmt_booking_cards(cards: list) -> str:
    lines = []
    for c in cards:
        ref = c.get("ref_number") or c.get("ref") or ""
        policy = c.get("policy_name") or c.get("plan") or "Policy"
        dest = c.get("destination") or ""
        dates = c.get("travel_dates") or c.get("dates") or ""
        premium = c.get("premium") or ""
        status = c.get("status") or ""
        insurer = c.get("insurer") or ""

        block = [f"📋 *Booking{' — ' + ref if ref else ''}*"]
        if policy:
            block.append(f"Plan: {policy}")
        if insurer:
            block.append(f"Insurer: {insurer}")
        if dest:
            block.append(f"Destination: {dest}")
        if dates:
            block.append(f"Dates: {dates}")
        if premium:
            block.append(f"Premium: {premium}")
        if status:
            block.append(f"Status: {status}")
        lines.append("\n".join(block))

    return "\n\n".join(lines)


def _fmt_confirm_card(data) -> str:
    """Booking confirmation request card."""
    if isinstance(data, list):
        data = data[0] if data else {}

    policy = data.get("policy_name") or data.get("plan") or "Policy"
    dest = data.get("destination") or ""
    dates = data.get("travel_dates") or ""
    adults = data.get("num_adults") or ""
    children = data.get("num_children") or ""
    premium = data.get("premium") or ""
    insurer = data.get("insurer") or ""

    lines = ["📋 *Booking Confirmation Request*\n"]
    lines.append(f"Plan: *{policy}*")
    if insurer:
        lines.append(f"Insurer: {insurer}")
    if dest:
        lines.append(f"Destination: {dest}")
    if dates:
        lines.append(f"Dates: {dates}")
    if adults or children:
        pax = f"{adults} adult(s)" if adults else ""
        if children:
            pax += f", {children} child(ren)"
        lines.append(f"Travellers: {pax}")
    if premium:
        lines.append(f"Premium: *{premium}*")
    lines.append("\nReply *Yes, confirm the booking* to proceed.")
    return "\n".join(lines)


def _fmt_booking_table(data) -> str:
    """Recent bookings table as plain text."""
    if isinstance(data, dict):
        bookings = data.get("bookings") or data.get("rows") or [data]
    elif isinstance(data, list):
        bookings = data
    else:
        return ""

    if not bookings:
        return "No recent bookings found."

    lines = ["*Recent Bookings:*\n"]
    for b in bookings[:5]:  # cap at 5 for readability
        ref = b.get("ref_number") or b.get("ref") or "—"
        dest = b.get("destination") or "—"
        dates = b.get("travel_dates") or "—"
        premium = b.get("premium") or "—"
        status = b.get("status") or "—"
        lines.append(f"• {ref} | {dest} | {dates} | {premium} | {status}")
    return "\n".join(lines)


_CARD_FORMATTERS = {
    "POLICY_CARDS": _fmt_policy_cards,
    "ADDON_CARDS": _fmt_addon_cards,
    "VAS_CARDS": _fmt_vas_cards,
    "BOOKING_CARDS": _fmt_booking_cards,
    "CONFIRM_BOOKING": _fmt_confirm_card,
    "BOOKING_TABLE": _fmt_booking_table,
}


def format_for_whatsapp(text: str) -> str:
    """
    Replace all embedded card blocks in *text* with WhatsApp-friendly plain text.
    Non-card text is preserved as-is (the agent already writes plain sentences).
    Returns the cleaned string ready to send via Meta Graph API.
    
    NOTE: This is the FALLBACK formatter. Use extract_interactive_messages() 
    to get native WhatsApp interactive lists/buttons instead.
    """
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        card_type = match.group(1).strip().upper()
        raw_data = match.group(2).strip()
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            return ""  # malformed card — remove silently

        formatter = _CARD_FORMATTERS.get(card_type)
        if formatter is None:
            return ""  # unknown card type — remove silently

        try:
            return formatter(data)
        except Exception:
            return ""  # never let a bad card crash the webhook

    result = _CARD_RE.sub(_replace, text)

    # Clean up any leftover HTML comment artifacts
    result = re.sub(r"<!--.*?-->", "", result, flags=re.DOTALL)

    # Collapse 3+ blank lines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


# ── Interactive Message Formatters (WhatsApp Native UI) ────────────────────────

def extract_interactive_messages(text: str) -> Dict[str, Union[str, List[Dict]]]:
    """
    Extract WhatsApp Interactive List/Button messages from agent response.
    
    Returns a dict with:
      - "text": The plain text with card markers removed
      - "interactive_list": List message payload (if POLICY_CARDS/ADDON_CARDS/VAS_CARDS found)
      - "interactive_buttons": Button message payload (if confirm-type POLICY_CARDS found)
      - "plain_text": Fallback plain text version (always present)
    
    If no interactive content is found, returns only plain_text.
    """
    if not text:
        return {"plain_text": ""}
    
    result = {
        "plain_text": format_for_whatsapp(text),
        "text": text,
        "interactive_list": None,
        "interactive_buttons": None,
    }
    
    # Extract first occurrence of each card type
    for match in _CARD_RE.finditer(text):
        card_type = match.group(1).strip().upper()
        raw_data = match.group(2).strip()
        
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            continue
        
        # Policy cards → Check if it's a confirm card or regular policy list
        if card_type == "POLICY_CARDS":
            cards_list = data if isinstance(data, list) else [data]
            # Check if it's a confirm card (type="confirm" or has destination/travelDates)
            first_card = cards_list[0] if cards_list else {}
            card_subtype = first_card.get("type", "").lower()
            is_confirm = (
                card_subtype == "confirm" or
                "destination" in first_card or
                "travelDates" in first_card or
                "travel_dates" in first_card
            )
            
            if is_confirm and result["interactive_buttons"] is None:
                result["interactive_buttons"] = _build_confirm_buttons(first_card)
            elif not is_confirm and result["interactive_list"] is None:
                result["interactive_list"] = _build_policy_list(cards_list)
        
        # Addon cards → Interactive List
        elif card_type == "ADDON_CARDS" and result["interactive_list"] is None:
            result["interactive_list"] = _build_addon_list(data)
        
        # VAS cards → Interactive List
        elif card_type == "VAS_CARDS" and result["interactive_list"] is None:
            result["interactive_list"] = _build_vas_list(data)
        
        # Legacy CONFIRM_BOOKING marker (keeping for backwards compatibility)
        elif card_type == "CONFIRM_BOOKING" and result["interactive_buttons"] is None:
            result["interactive_buttons"] = _build_confirm_buttons(data)
    
    # Remove card markers from text
    clean_text = _CARD_RE.sub("", text)
    clean_text = re.sub(r"<!--.*?-->", "", clean_text, flags=re.DOTALL)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    result["text"] = clean_text
    
    return result


def _build_policy_list_fallback(cards_list: List[Dict]) -> Dict:
    """
    Build fallback Interactive List for policy cards when catalog is not available.
    Used when product catalog is not set up or carousel fails.
    """
    # WhatsApp allows max 10 items per list
    cards_list = cards_list[:10]
    
    rows = []
    for i, card in enumerate(cards_list, 1):
        name = card.get("name") or card.get("plan_name") or f"Plan {i}"
        insurer = card.get("insurer") or card.get("provider") or ""
        premium = card.get("premium") or card.get("price") or ""
        cover = card.get("sum_insured") or card.get("coverage") or card.get("cover") or ""
        
        # Title: max 24 chars
        title = name[:24]
        
        # Description: max 72 chars
        desc_parts = []
        if premium:
            desc_parts.append(f"₹{premium}" if not str(premium).startswith("₹") else str(premium))
        if cover:
            desc_parts.append(f"Cover: {cover}")
        elif insurer:
            desc_parts.append(insurer)
        
        description = " | ".join(desc_parts)[:72]
        
        rows.append({
            "id": f"policy_{i}",
            "title": title,
            "description": description or "Travel Insurance Plan"
        })
    
    return {
        "type": "list",
        "header": {"type": "text", "text": "🛡️ Travel Insurance Plans"},
        "body": {"text": "Choose the best plan for your journey. Tap below to view all available options."},
        "footer": {"text": "Powered by Dolphin Buddy 🐬"},
        "action": {
            "button": "View Plans",
            "sections": [{
                "title": "Available Plans",
                "rows": rows
            }]
        }
    }


def _build_policy_list(cards: Union[List, Dict]) -> Dict:
    """
    Build WhatsApp Multi-Product Carousel for policy cards.
    
    Returns a product_list interactive message that shows policy cards
    as a horizontal carousel with images (if catalog is set up).
    Falls back to regular list if no catalog.
    """
    cards_list = cards if isinstance(cards, list) else [cards]
    
    # WhatsApp allows max 30 products in carousel, but practical limit is 10
    cards_list = cards_list[:10]
    
    # Build product items for carousel
    product_items = []
    
    for i, card in enumerate(cards_list, 1):
        name = card.get("name") or card.get("plan_name") or f"Plan {i}"
        insurer = card.get("insurer") or card.get("provider") or ""
        premium = card.get("premium") or card.get("price") or ""
        cover = card.get("sum_insured") or card.get("coverage") or card.get("cover") or ""
        
        # Create a product retailer ID from the policy name
        # This should match products in your WhatsApp catalog
        # Format: lowercase, replace spaces with underscores
        product_id = name.lower().replace(" ", "_").replace("-", "_")[:100]
        
        product_items.append({
            "product_retailer_id": product_id
        })
    
    # Multi-Product Message (Carousel)
    return {
        "type": "product_list",
        "header": {
            "type": "text",
            "text": "🛡️ Travel Insurance"
        },
        "body": {
            "text": "Swipe through our recommended plans. Each plan includes comprehensive coverage and 24/7 support."
        },
        "footer": {
            "text": "Powered by Dolphin Buddy 🐬"
        },
        "action": {
            "catalog_id": "${CATALOG_ID}",  # Placeholder - will be replaced from env
            "sections": [{
                "title": "Recommended Plans",
                "product_items": product_items
            }]
        },
        # Store original card data for fallback
        "_fallback_data": cards_list
    }


def _build_addon_list(cards: Union[List, Dict]) -> Dict:
    """Build WhatsApp Interactive List for addon cards."""
    cards_list = cards if isinstance(cards, list) else [cards]
    cards_list = cards_list[:10]
    
    rows = []
    for i, card in enumerate(cards_list, 1):
        name = card.get("name") or card.get("title") or f"Addon {i}"
        price = card.get("price") or card.get("premium") or ""
        desc = card.get("description") or card.get("desc") or ""
        
        title = name[:24]
        
        desc_parts = []
        if price:
            desc_parts.append(f"₹{price}" if not str(price).startswith("₹") else str(price))
        if desc:
            desc_parts.append(desc[:50])
        
        description = " | ".join(desc_parts)[:72] or "Add-on Coverage"
        
        rows.append({
            "id": f"addon_{i}",
            "title": title,
            "description": description
        })
    
    return {
        "type": "list",
        "header": {"type": "text", "text": "✨ Available Add-ons"},
        "body": {"text": "Enhance your coverage with these optional add-ons. Tap below to see all options."},
        "footer": {"text": "Powered by Dolphin Buddy 🐬"},
        "action": {
            "button": "View Add-ons",
            "sections": [{
                "title": "Add-on Options",
                "rows": rows
            }]
        }
    }


def _build_vas_list(cards: Union[List, Dict]) -> Dict:
    """Build WhatsApp Interactive List for VAS cards."""
    cards_list = cards if isinstance(cards, list) else [cards]
    cards_list = cards_list[:10]
    
    rows = []
    for i, card in enumerate(cards_list, 1):
        name = card.get("name") or card.get("title") or f"Service {i}"
        price = card.get("price") or card.get("cost") or ""
        desc = card.get("description") or card.get("desc") or ""
        
        title = name[:24]
        
        desc_parts = []
        if price:
            desc_parts.append(f"₹{price}" if not str(price).startswith("₹") else str(price))
        if desc:
            desc_parts.append(desc[:50])
        
        description = " | ".join(desc_parts)[:72] or "Value Added Service"
        
        rows.append({
            "id": f"vas_{i}",
            "title": title,
            "description": description
        })
    
    return {
        "type": "list",
        "header": {"type": "text", "text": "💼 Value Added Services"},
        "body": {"text": "Premium services to make your travel experience seamless. Tap below to explore."},
        "footer": {"text": "Powered by Dolphin Buddy 🐬"},
        "action": {
            "button": "View Services",
            "sections": [{
                "title": "VAS Options",
                "rows": rows
            }]
        }
    }


def _build_confirm_buttons(data: Union[List, Dict]) -> Dict:
    """Build WhatsApp Interactive Buttons for booking confirmation."""
    card = data[0] if isinstance(data, list) else data
    
    # Handle both field naming conventions
    policy = (
        card.get("name") or 
        card.get("policy_name") or 
        card.get("plan") or 
        "Policy"
    )
    company = card.get("company") or card.get("insurer") or ""
    dest = card.get("destination") or ""
    dates = card.get("travelDates") or card.get("travel_dates") or ""
    travellers = card.get("travellers") or ""
    adults = card.get("num_adults") or ""
    children = card.get("num_children") or ""
    premium = card.get("premium") or ""
    sum_insured = card.get("sumInsured") or card.get("sum_insured") or ""
    
    # Build travellers string if not provided
    if not travellers and (adults or children):
        pax = f"{adults} adult(s)" if adults else ""
        if children:
            pax += f", {children} child(ren)" if pax else f"{children} child(ren)"
        travellers = pax
    
    # Build message body
    lines = ["📋 *Booking Confirmation*\n"]
    lines.append(f"*Plan:* {policy}")
    if company:
        lines.append(f"*Insurer:* {company}")
    if dest:
        lines.append(f"*Destination:* {dest}")
    if dates:
        lines.append(f"*Dates:* {dates}")
    if travellers:
        lines.append(f"*Travellers:* {travellers}")
    if sum_insured:
        lines.append(f"*Cover:* {sum_insured}")
    if premium:
        lines.append(f"\n*Total Premium:* {premium}")
    
    body_text = "\n".join(lines)
    
    return {
        "type": "button",
        "body": {"text": body_text},
        "footer": {"text": "Choose an action below"},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {
                        "id": "confirm_booking",
                        "title": "✅ Confirm"
                    }
                },
                {
                    "type": "reply",
                    "reply": {
                        "id": "modify_booking",
                        "title": "✏️ Modify"
                    }
                },
                {
                    "type": "reply",
                    "reply": {
                        "id": "cancel_booking",
                        "title": "❌ Cancel"
                    }
                }
            ]
        }
    }


def extract_artifact_filenames(text: str) -> list[str]:
    """
    Pull artifact filenames referenced in the agent response so the webhook
    can send them as WhatsApp document messages.

    The agent references artifacts either:
      - In card JSON as  "artifact": "booking_confirmation.pdf"
      - As bare PDF filenames mentioned in the text
    """
    filenames: list[str] = []

    # 1. Scan all card JSON payloads
    for match in _CARD_RE.finditer(text):
        try:
            data = json.loads(match.group(2))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        _collect_pdf_values(item, filenames)
            elif isinstance(data, dict):
                _collect_pdf_values(data, filenames)
        except Exception:
            pass

    # 2. Bare PDF filenames in plain text  (e.g. "booking_confirmation_BUD-ABC.pdf")
    for m in re.finditer(r"\b[\w\-]+\.pdf\b", text, re.IGNORECASE):
        fname = m.group(0)
        if fname not in filenames:
            filenames.append(fname)

    return filenames


def _collect_pdf_values(obj: dict, out: list[str]):
    """Recursively collect string values that look like PDF filenames."""
    for v in obj.values():
        if isinstance(v, str) and v.lower().endswith(".pdf") and v not in out:
            out.append(v)
        elif isinstance(v, dict):
            _collect_pdf_values(v, out)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _collect_pdf_values(item, out)
