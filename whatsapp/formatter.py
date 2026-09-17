"""
WhatsApp plain-text formatter.

Takes the agent's raw response string (which may contain embedded card markers
like <!--POLICY_CARDS:[...]-->) and produces clean, readable plain text
suitable for WhatsApp.

WhatsApp does NOT render markdown tables, HTML, or custom JSON blocks.
It does render *bold* (asterisks) and _italic_ (underscores), which we use
sparingly for headers and key fields.

Card types handled:
  POLICY_CARDS        → numbered list of policy options
  ADDON_CARDS         → bulleted addon options
  VAS_CARDS           → bulleted VAS options
  BOOKING_CARDS       → booking summary block
  BOOKING_TABLE       → tabular booking list as text
  CONFIRM_BOOKING     → booking confirmation request
  Any unknown card    → stripped silently (never crashes)

PDF artifacts are NOT handled here — they are sent as WhatsApp document
messages by the webhook handler after it collects artifact filenames.
"""
import json
import re
from typing import Optional


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
