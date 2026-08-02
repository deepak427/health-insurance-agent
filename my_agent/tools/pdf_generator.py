from fpdf import FPDF
import google.genai.types as types
from google.adk.tools import ToolContext


def _safe(text: str) -> str:
    """Replace characters outside latin-1 range with safe ASCII equivalents."""
    return (
        text
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "*")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2019", "'")
        .replace("\u00b7", "*")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


# ── Brand Colours (matching Dolphin Buddy frontend) ────────────────────────────
# Primary dark background:  stone-950  → (12, 10, 9)
# Card/surface background:  stone-900  → (28, 25, 23)
# Section surface:          stone-800  → (41, 37, 36)
# Accent emerald:           #0f5132    → (15, 81, 50)
# Accent teal highlight:    #0d9488    → (13, 148, 136)
# Text primary:             stone-100  → (245, 245, 244)
# Text muted:               stone-400  → (168, 162, 158)
# Border subtle:            stone-700  → (68, 64, 60)

_DARK_BG      = (12, 10, 9)
_CARD_BG      = (28, 25, 23)
_SECTION_BG   = (41, 37, 36)
_BORDER       = (68, 64, 60)
_ACCENT       = (15, 81, 50)        # emerald-800
_ACCENT_LIGHT = (16, 185, 129)      # emerald-500 — for highlights
_TEAL         = (13, 148, 136)
_TEXT_PRIMARY = (245, 245, 244)
_TEXT_MUTED   = (168, 162, 158)
_TEXT_DIM     = (120, 113, 108)
_WHITE        = (255, 255, 255)


class DolphinPDF(FPDF):
    """Custom FPDF subclass with Dolphin Buddy dark theme."""

    def header(self):
        """Intentionally empty — we draw a custom branded header in _build_pdf."""
        pass

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*_TEXT_DIM)
        left = "Dolphin Buddy  |  AI Insurance Support"
        right = f"Page {self.page_no()}"
        self.cell(0, 6, _safe(left), align="L")
        self.set_y(-18)
        self.cell(0, 6, _safe(right), align="R")
        # thin separator line above footer
        self.set_draw_color(*_BORDER)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.h - 20, self.w - self.r_margin, self.h - 20)


def _draw_shield(pdf: FPDF, cx: float, cy: float, size: float = 10.0):
    """Draw a simple shield shape filled with emerald accent colour."""
    # Shield = rounded rectangle top + triangle bottom
    w = size * 0.75
    h = size
    x = cx - w / 2
    y = cy - h / 2

    pdf.set_fill_color(*_ACCENT)
    pdf.set_draw_color(*_ACCENT_LIGHT)
    pdf.set_line_width(0.4)

    # Top rounded rect (approximated with a rect + ellipse cap)
    pdf.rect(x, y, w, h * 0.65, style="F")
    # Bottom triangle point: draw filled polygon via lines
    # (fpdf2 supports polygon — use three cells approximation)
    # Simple approach: draw a solid rect that tapers — use ellipse for bottom cap
    tip_y = y + h
    mid_x = cx
    pdf.set_fill_color(*_ACCENT_LIGHT)
    # small highlight dot in centre of shield
    pdf.ellipse(mid_x - 1.2, y + h * 0.15, 2.4, 2.4, style="F")


def _build_pdf(title: str, sections: list[dict]) -> bytes:
    """Builds a styled Dolphin Buddy dark-theme PDF and returns raw bytes."""

    pdf = DolphinPDF()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    # ── Full-page dark background ──────────────────────────────────────────────
    pdf.set_fill_color(*_DARK_BG)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")

    # ── Top branded header bar ─────────────────────────────────────────────────
    header_h = 28
    pdf.set_fill_color(*_CARD_BG)
    pdf.rect(0, 0, pdf.w, header_h, style="F")

    # Emerald left accent stripe
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(0, 0, 4, header_h, style="F")

    # Brand name: "DolphinBuddy"
    pdf.set_xy(10, 6)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*_ACCENT_LIGHT)
    pdf.cell(32, 8, "Dolphin", ln=0)
    pdf.set_text_color(*_TEXT_PRIMARY)
    pdf.cell(22, 8, "Buddy", ln=0)

    # Tagline
    pdf.set_xy(10, 15)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*_TEXT_MUTED)
    pdf.cell(80, 5, "AI Insurance Support  *  insurance.dolphinbuddy.ai")

    # "VERIFIED" badge on the right
    badge_x = pdf.w - 48
    badge_y = 8
    badge_w = 36
    badge_h = 11
    pdf.set_fill_color(*_ACCENT)
    pdf.set_draw_color(*_ACCENT_LIGHT)
    pdf.set_line_width(0.5)
    pdf.rect(badge_x, badge_y, badge_w, badge_h, style="FD")
    pdf.set_xy(badge_x, badge_y + 1.5)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*_ACCENT_LIGHT)
    pdf.cell(badge_w, 7, "* OFFICIAL GUIDE", align="C")

    # thin bottom border for header
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(0, header_h, pdf.w, header_h)

    # ── Document title block ───────────────────────────────────────────────────
    pdf.set_xy(pdf.l_margin, header_h + 8)

    # Title pill background
    title_block_h = 18
    pdf.set_fill_color(*_SECTION_BG)
    pdf.rect(pdf.l_margin - 2, header_h + 6, page_w + 4, title_block_h, style="F")

    pdf.set_xy(pdf.l_margin, header_h + 9)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*_TEXT_PRIMARY)
    pdf.cell(page_w, 10, _safe(title), align="C")

    # thin emerald underline
    underline_y = header_h + 6 + title_block_h
    pdf.set_draw_color(*_ACCENT_LIGHT)
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin + 20, underline_y, pdf.w - pdf.r_margin - 20, underline_y)

    pdf.set_y(underline_y + 6)

    # ── Sections ───────────────────────────────────────────────────────────────
    for section in sections:
        # Section heading pill
        pdf.set_x(pdf.l_margin)
        heading_y = pdf.get_y()
        heading_h = 10

        pdf.set_fill_color(*_CARD_BG)
        pdf.set_draw_color(*_BORDER)
        pdf.set_line_width(0.3)
        pdf.rect(pdf.l_margin - 2, heading_y, page_w + 4, heading_h, style="FD")

        # Emerald left accent for heading
        pdf.set_fill_color(*_ACCENT_LIGHT)
        pdf.rect(pdf.l_margin - 2, heading_y, 3, heading_h, style="F")

        pdf.set_xy(pdf.l_margin + 4, heading_y + 1.5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_ACCENT_LIGHT)
        pdf.cell(page_w - 6, 7, _safe(section["heading"]))

        pdf.set_y(heading_y + heading_h + 3)

        # Section body lines
        pdf.set_font("Helvetica", "", 10)
        for line in section["lines"]:
            safe_line = _safe(line)
            is_bullet = safe_line.startswith(("-", "*", "•", "~"))

            if is_bullet:
                # Bullet indicator dot
                dot_x = pdf.l_margin + 4
                dot_y = pdf.get_y() + 3.5
                pdf.set_fill_color(*_ACCENT_LIGHT)
                pdf.ellipse(dot_x, dot_y, 2, 2, style="F")

                pdf.set_x(pdf.l_margin + 9)
                pdf.set_text_color(*_TEXT_PRIMARY)
                # Strip bullet char and leading space
                stripped = safe_line.lstrip("-*•~ ").strip()
                pdf.multi_cell(page_w - 9, 6.5, stripped)
            else:
                pdf.set_x(pdf.l_margin)
                pdf.set_text_color(*_TEXT_MUTED)
                pdf.multi_cell(page_w, 6.5, safe_line)

        pdf.ln(5)

        # thin rule between sections
        pdf.set_draw_color(*_BORDER)
        pdf.set_line_width(0.25)
        pdf.line(pdf.l_margin, pdf.get_y() - 2, pdf.w - pdf.r_margin, pdf.get_y() - 2)
        pdf.ln(2)

    # ── Bottom disclaimer block ────────────────────────────────────────────────
    pdf.ln(4)
    disc_y = pdf.get_y()
    pdf.set_fill_color(*_CARD_BG)
    pdf.set_draw_color(*_BORDER)
    pdf.set_line_width(0.3)
    pdf.rect(pdf.l_margin - 2, disc_y, page_w + 4, 12, style="FD")
    pdf.set_xy(pdf.l_margin + 2, disc_y + 2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*_TEXT_DIM)
    pdf.multi_cell(
        page_w - 4, 4.5,
        "This document is generated by Dolphin Buddy AI for informational purposes only. "
        "It does not constitute professional insurance advice. Always consult a licensed "
        "insurance professional for decisions specific to your situation.",
    )

    return bytes(pdf.output())


async def generate_insurance_summary_pdf(
    insurance_type: str,
    tool_context: ToolContext,
) -> dict:
    """
    Generates a PDF summary guide for a given insurance type and saves it as an artifact.
    Use this when the user asks for a downloadable guide, summary, or reference document
    about an insurance topic.

    Args:
        insurance_type (str): The type of insurance to generate a guide for.
                              E.g. 'health', 'auto', 'home', 'life', 'travel'.

    Returns:
        dict: Status and the artifact filename where the PDF was saved.
    """
    guides = {
        "health": {
            "title": "Health Insurance - Complete Guide",
            "sections": [
                {
                    "heading": "What is Health Insurance?",
                    "lines": [
                        "Health insurance covers medical expenses including doctor visits,",
                        "hospital stays, surgeries, prescription drugs, and preventive care.",
                    ],
                },
                {
                    "heading": "Key Terms",
                    "lines": [
                        "- Premium: Your monthly payment to keep the policy active.",
                        "- Deductible: Amount you pay before insurance kicks in.",
                        "- Copay: Fixed fee per visit (e.g. $20 for a doctor visit).",
                        "- Coinsurance: Your share after deductible (e.g. 20% of costs).",
                        "- Out-of-Pocket Maximum: The most you'll pay in a year.",
                        "- Network: Doctors/hospitals that have agreements with your insurer.",
                    ],
                },
                {
                    "heading": "Plan Types",
                    "lines": [
                        "- HMO (Health Maintenance Organization): Requires referrals, lower cost.",
                        "- PPO (Preferred Provider Organization): More flexibility, higher cost.",
                        "- EPO: Like PPO but no out-of-network coverage.",
                        "- HDHP (High Deductible Health Plan): Paired with HSA savings account.",
                    ],
                },
                {
                    "heading": "Tips for Choosing a Plan",
                    "lines": [
                        "- Check if your current doctors are in-network.",
                        "- Estimate your yearly medical usage before picking a deductible.",
                        "- Consider an HDHP + HSA if you're generally healthy.",
                        "- Always check prescription drug coverage.",
                    ],
                },
            ],
        },
        "auto": {
            "title": "Auto Insurance - Complete Guide",
            "sections": [
                {
                    "heading": "What is Auto Insurance?",
                    "lines": [
                        "Auto insurance protects you financially in case of accidents,",
                        "theft, or damage to your vehicle or others' property.",
                    ],
                },
                {
                    "heading": "Coverage Types",
                    "lines": [
                        "- Liability: Covers damage/injury you cause to others. Usually required by law.",
                        "- Collision: Covers your car damage in an accident regardless of fault.",
                        "- Comprehensive: Covers theft, weather, fire, animal damage.",
                        "- Uninsured Motorist: Protects you if hit by an uninsured driver.",
                        "- PIP / Medical Payments: Covers medical costs for you and passengers.",
                    ],
                },
                {
                    "heading": "What Affects Your Premium?",
                    "lines": [
                        "- Your driving record (accidents, tickets)",
                        "- Age and experience",
                        "- Vehicle make, model, and year",
                        "- Where you live and park",
                        "- Annual mileage",
                        "- Credit score (in most states)",
                    ],
                },
                {
                    "heading": "Tips",
                    "lines": [
                        "- Bundle auto + home insurance for discounts.",
                        "- Raise your deductible to lower premiums.",
                        "- Ask about safe driver, good student, or low-mileage discounts.",
                    ],
                },
            ],
        },
        "home": {
            "title": "Home Insurance - Complete Guide",
            "sections": [
                {
                    "heading": "What is Home Insurance?",
                    "lines": [
                        "Home insurance protects your home's structure and personal belongings",
                        "and provides liability coverage if someone is injured on your property.",
                    ],
                },
                {
                    "heading": "What's Covered",
                    "lines": [
                        "- Dwelling: The physical structure of your home.",
                        "- Other Structures: Garages, fences, sheds.",
                        "- Personal Property: Furniture, electronics, clothing.",
                        "- Liability: Legal costs if someone is hurt on your property.",
                        "- Additional Living Expenses: Temporary housing if home is uninhabitable.",
                    ],
                },
                {
                    "heading": "What's NOT Covered",
                    "lines": [
                        "- Floods - requires a separate flood insurance policy.",
                        "- Earthquakes - requires a separate earthquake policy.",
                        "- Normal wear and tear.",
                        "- Pest or insect damage.",
                    ],
                },
                {
                    "heading": "Tips",
                    "lines": [
                        "- Keep a home inventory with photos and receipts.",
                        "- Review your policy limits annually.",
                        "- Consider replacement cost vs. actual cash value coverage.",
                    ],
                },
            ],
        },
        "life": {
            "title": "Life Insurance - Complete Guide",
            "sections": [
                {
                    "heading": "What is Life Insurance?",
                    "lines": [
                        "Life insurance pays a benefit to your beneficiaries when you pass away,",
                        "helping replace income and cover expenses like mortgage and education.",
                    ],
                },
                {
                    "heading": "Types of Life Insurance",
                    "lines": [
                        "- Term Life: Coverage for a set period (10-30 years). Most affordable.",
                        "- Whole Life: Permanent coverage with a cash value component.",
                        "- Universal Life: Flexible premiums and death benefits.",
                        "- Variable Life: Tied to investment accounts, higher risk/reward.",
                    ],
                },
                {
                    "heading": "How Much Coverage Do You Need?",
                    "lines": [
                        "- Common rule: 10-12x your annual income.",
                        "- Factor in: mortgage, debts, childcare, education costs.",
                        "- Online calculators can give a more precise number.",
                    ],
                },
                {
                    "heading": "Tips",
                    "lines": [
                        "- Buy early - premiums are much lower when you're young and healthy.",
                        "- Review and update beneficiaries after life events.",
                        "- Term life is usually the best starting point for most families.",
                    ],
                },
            ],
        },
        "travel": {
            "title": "Travel Insurance - Complete Guide",
            "sections": [
                {
                    "heading": "What is Travel Insurance?",
                    "lines": [
                        "Travel insurance protects you from financial losses while traveling,",
                        "including trip cancellations, medical emergencies, and lost luggage.",
                    ],
                },
                {
                    "heading": "What's Typically Covered",
                    "lines": [
                        "- Trip cancellation / interruption",
                        "- Emergency medical expenses abroad",
                        "- Medical evacuation",
                        "- Lost, stolen, or delayed baggage",
                        "- Travel delay reimbursement",
                        "- Accidental death and dismemberment",
                    ],
                },
                {
                    "heading": "When You Need It Most",
                    "lines": [
                        "- International travel where your health plan doesn't apply.",
                        "- Expensive non-refundable trips.",
                        "- Travel to regions with political instability or health risks.",
                    ],
                },
                {
                    "heading": "Tips",
                    "lines": [
                        "- Buy travel insurance immediately after booking your trip.",
                        "- Check if your credit card already provides travel coverage.",
                        "- Read the fine print on cancel-for-any-reason clauses.",
                    ],
                },
            ],
        },
    }

    key = insurance_type.lower().strip()
    matched = None
    for k in guides:
        if key in k or k in key:
            matched = k
            break

    if not matched:
        return {
            "status": "error",
            "message": f"No guide available for '{insurance_type}'. Try: health, auto, home, life, travel.",
        }

    guide = guides[matched]
    pdf_bytes = _build_pdf(guide["title"], guide["sections"])

    artifact = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    filename = f"{matched}_insurance_guide.pdf"
    version = await tool_context.save_artifact(filename=filename, artifact=artifact)

    return {
        "status": "success",
        "message": f"PDF guide generated and saved.",
        "filename": filename,
        "version": version,
        "size_bytes": len(pdf_bytes),
        "instruction": f"Tell the user their '{guide['title']}' PDF is ready and available as artifact '{filename}'.",
    }
