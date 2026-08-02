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
        .replace("\u00b7", "*")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


# ── Brand Colours (Dolphin Buddy — Calm Coastal Soft Editorial) ────────────────
#
#  Warm Oat background:   #f9f8f6  → (249, 248, 246)
#  Pebble surface:        #f1efe9  → (241, 239, 233)
#  Card white:            #ffffff  → (255, 255, 255)
#  Deep Sage accent:      #5b7c72  → ( 91, 124, 114)
#  Sage hover:            #4a665d  → ( 74, 102,  93)
#  Soft Coral highlight:  #e8a598  → (232, 165, 152)
#  Warm Sand:             #d4c5b9  → (212, 197, 185)
#  Soft border:           #e2ded7  → (226, 222, 215)
#  Border highlight:      #d1ccc4  → (209, 204, 196)
#  Espresso text:         #2c2a29  → ( 44,  42,  41)
#  Warm grey muted:       #797571  → (121, 117, 113)
#  Lighter dim:           #9e9a95  → (158, 154, 149)

_OAT        = (249, 248, 246)   # main background
_PEBBLE     = (241, 239, 233)   # section / sidebar surface
_WHITE      = (255, 255, 255)   # card surfaces
_SAGE       = ( 91, 124, 114)   # primary accent (Deep Sage)
_CORAL      = (232, 165, 152)   # soft coral highlight
_SAND       = (212, 197, 185)   # warm sand secondary
_BORDER     = (226, 222, 215)   # soft border
_BORDER2    = (209, 204, 196)   # slightly darker border
_TEXT       = ( 44,  42,  41)   # espresso — main text
_MUTED      = (121, 117, 113)   # warm grey — secondary text
_DIM        = (158, 154, 149)   # lighter dim — timestamps etc.


class DolphinPDF(FPDF):
    """FPDF subclass with Dolphin Buddy soft editorial theme."""

    def header(self):
        # Intentionally blank — branded header drawn once in _build_pdf
        pass

    def footer(self):
        self.set_y(-16)
        # Thin rule
        self.set_draw_color(*_BORDER)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.h - 17, self.w - self.r_margin, self.h - 17)

        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*_DIM)
        self.cell(0, 6, _safe("Dolphin Buddy  |  AI Insurance Support"), align="L")
        self.set_y(-16)
        self.cell(0, 6, _safe(f"Page {self.page_no()}"), align="R")


def _build_pdf(title: str, sections: list[dict]) -> bytes:
    """Build an airy, soft-editorial PDF matching the Dolphin Buddy UI."""

    pdf = DolphinPDF()
    pdf.set_auto_page_break(auto=True, margin=24)
    pdf.add_page()

    pw = pdf.w - pdf.l_margin - pdf.r_margin   # usable page width

    # ── Full-page warm oat background ─────────────────────────────────────────
    pdf.set_fill_color(*_OAT)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")

    # ── Header band (pebble surface) ──────────────────────────────────────────
    hdr_h = 30
    pdf.set_fill_color(*_PEBBLE)
    pdf.rect(0, 0, pdf.w, hdr_h, style="F")

    # Sage left accent stripe
    pdf.set_fill_color(*_SAGE)
    pdf.rect(0, 0, 5, hdr_h, style="F")

    # Coral bottom accent line on header
    pdf.set_fill_color(*_CORAL)
    pdf.rect(0, hdr_h - 1.5, pdf.w, 1.5, style="F")

    # Brand — "Dolphin Buddy"
    pdf.set_xy(12, 8)
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_SAGE)
    pdf.cell(30, 7, "Dolphin", ln=0)
    pdf.set_text_color(*_TEXT)
    pdf.cell(24, 7, " Buddy", ln=0)

    # Tagline
    pdf.set_xy(12, 18)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*_MUTED)
    pdf.cell(80, 5, "AI Insurance Support")

    # Small coral badge top-right
    badge_w, badge_h = 38, 10
    bx = pdf.w - badge_w - 8
    by = (hdr_h - badge_h) / 2
    pdf.set_fill_color(*_CORAL)
    pdf.set_draw_color(*_CORAL)
    pdf.rect(bx, by, badge_w, badge_h, style="F")
    pdf.set_xy(bx, by + 1.5)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*_WHITE)
    pdf.cell(badge_w, 7, "OFFICIAL GUIDE", align="C")

    # ── Title block ───────────────────────────────────────────────────────────
    pdf.set_y(hdr_h + 10)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(pw, 11, _safe(title), align="L")

    # Sage underline beneath title
    ul_y = pdf.get_y() + 3
    pdf.set_draw_color(*_SAGE)
    pdf.set_line_width(1.5)
    pdf.line(pdf.l_margin, ul_y, pdf.l_margin + 50, ul_y)
    # Coral continuation
    pdf.set_draw_color(*_CORAL)
    pdf.set_line_width(1.5)
    pdf.line(pdf.l_margin + 52, ul_y, pdf.l_margin + 68, ul_y)

    pdf.set_y(ul_y + 8)

    # ── Sections ──────────────────────────────────────────────────────────────
    for section in sections:
        # Section heading pill on white card
        heading = _safe(section["heading"])
        h_y = pdf.get_y()
        card_h = 12

        pdf.set_fill_color(*_WHITE)
        pdf.set_draw_color(*_BORDER)
        pdf.set_line_width(0.25)
        pdf.rect(pdf.l_margin - 2, h_y, pw + 4, card_h, style="FD")

        # Sage left pill accent
        pdf.set_fill_color(*_SAGE)
        pdf.rect(pdf.l_margin - 2, h_y, 3.5, card_h, style="F")

        pdf.set_xy(pdf.l_margin + 5, h_y + 2.5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_SAGE)
        pdf.cell(pw - 10, 7, heading)

        pdf.set_y(h_y + card_h + 5)

        # Section body
        for line in section["lines"]:
            safe_line = _safe(line)
            is_bullet = safe_line.startswith(("-", "*"))

            if is_bullet:
                # Coral soft dot
                dot_x = pdf.l_margin + 4
                dot_y = pdf.get_y() + 3.2
                pdf.set_fill_color(*_CORAL)
                pdf.ellipse(dot_x, dot_y, 2.2, 2.2, style="F")

                pdf.set_x(pdf.l_margin + 10)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*_TEXT)
                stripped = safe_line.lstrip("-* ").strip()
                pdf.multi_cell(pw - 10, 6.5, stripped)
            else:
                pdf.set_x(pdf.l_margin + 2)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*_MUTED)
                pdf.multi_cell(pw - 2, 6.5, safe_line)

        pdf.ln(4)

        # Subtle divider between sections
        div_y = pdf.get_y()
        pdf.set_draw_color(*_BORDER)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, div_y, pdf.w - pdf.r_margin, div_y)
        pdf.ln(5)

    # ── Disclaimer card ───────────────────────────────────────────────────────
    pdf.ln(2)
    disc_y = pdf.get_y()
    disc_h = 14
    pdf.set_fill_color(*_PEBBLE)
    pdf.set_draw_color(*_BORDER)
    pdf.set_line_width(0.25)
    pdf.rect(pdf.l_margin - 2, disc_y, pw + 4, disc_h, style="FD")

    pdf.set_xy(pdf.l_margin + 4, disc_y + 2.5)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        pw - 8, 4.5,
        "This document is generated by Dolphin Buddy AI for informational purposes only. "
        "It does not constitute professional insurance advice. Consult a licensed "
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
            "title": "Health Insurance\nComplete Guide",
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
                        "- Out-of-Pocket Maximum: The most you will pay in a year.",
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
                        "- Consider an HDHP + HSA if you are generally healthy.",
                        "- Always check prescription drug coverage.",
                    ],
                },
            ],
        },
        "auto": {
            "title": "Auto Insurance\nComplete Guide",
            "sections": [
                {
                    "heading": "What is Auto Insurance?",
                    "lines": [
                        "Auto insurance protects you financially in case of accidents,",
                        "theft, or damage to your vehicle or others property.",
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
            "title": "Home Insurance\nComplete Guide",
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
                        "- Floods: Requires a separate flood insurance policy.",
                        "- Earthquakes: Requires a separate earthquake policy.",
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
            "title": "Life Insurance\nComplete Guide",
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
                        "- Review and update beneficiaries after major life events.",
                        "- Term life is usually the best starting point for most families.",
                    ],
                },
            ],
        },
        "travel": {
            "title": "Travel Insurance\nComplete Guide",
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
                        "- Trip cancellation and interruption",
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
                        "- International travel where your health plan does not apply.",
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
        "message": "PDF guide generated and saved.",
        "filename": filename,
        "version": version,
        "size_bytes": len(pdf_bytes),
        "instruction": f"Tell the user their '{guide['title'].replace(chr(10), ' ')}' PDF is ready and available as artifact '{filename}'.",
    }
