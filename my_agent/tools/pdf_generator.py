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


# ── Brand Colours (Dolphin Buddy Portal) ──────────────────────────────────────
#
#  Navy sidebar:      #0b192c  → ( 11,  25,  44)
#  Emerald primary:   #00a86b  → (  0, 168, 107)
#  Emerald hover:     #008f5a  → (  0, 143,  90)
#  Emerald light bg:  #dcf8c6  → (220, 248, 198)   ← user bubble tint
#  Light gray bg:     #f8fafc  → (248, 250, 252)   ← chat stream bg
#  White card:        #ffffff  → (255, 255, 255)
#  Border:            #e5e7eb  → (229, 231, 235)
#  Text main:         #1f2937  → ( 31,  41,  55)
#  Text muted:        #6b7280  → (107, 114, 128)
#  Text dim:          #9ca3af  → (156, 163, 175)

_NAVY           = ( 11,  25,  44)
_EMERALD        = (  0, 168, 107)
_EMERALD_DARK   = (  0, 143,  90)
_EMERALD_LIGHT  = (220, 248, 198)
_BG_LIGHT       = (248, 250, 252)
_WHITE          = (255, 255, 255)
_BORDER         = (229, 231, 235)
_TEXT           = ( 31,  41,  55)
_MUTED          = (107, 114, 128)
_DIM            = (156, 163, 175)


class DolphinPDF(FPDF):
    """FPDF subclass with Dolphin Buddy portal theme."""

    def header(self):
        pass  # drawn manually in _build_pdf

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
    """Build a PDF matching the Dolphin Buddy portal UI theme."""

    pdf = DolphinPDF()
    pdf.set_auto_page_break(auto=True, margin=24)
    pdf.add_page()

    pw = pdf.w - pdf.l_margin - pdf.r_margin   # usable page width

    # ── Full-page light background ─────────────────────────────────────────────
    pdf.set_fill_color(*_BG_LIGHT)
    pdf.rect(0, 0, pdf.w, pdf.h, style="F")

    # ── Header band — navy ─────────────────────────────────────────────────────
    hdr_h = 32
    pdf.set_fill_color(*_NAVY)
    pdf.rect(0, 0, pdf.w, hdr_h, style="F")

    # Emerald left accent stripe
    pdf.set_fill_color(*_EMERALD)
    pdf.rect(0, 0, 5, hdr_h, style="F")

    # Emerald bottom accent line
    pdf.set_fill_color(*_EMERALD)
    pdf.rect(0, hdr_h - 2, pdf.w, 2, style="F")

    # Draw the chat-bubble logo shape (simplified as coloured rect + dots)
    logo_x, logo_y = 12, 7
    logo_w, logo_h = 22, 12
    pdf.set_fill_color(*_EMERALD)
    # Bubble rect
    pdf.rect(logo_x, logo_y, logo_w, logo_h, style="F")
    # Bubble tail (small triangle implied by tiny rect offset)
    pdf.rect(logo_x + 1, logo_y + logo_h, 5, 2.5, style="F")
    # Three white dots
    dot_y = logo_y + logo_h / 2 - 1
    pdf.set_fill_color(*_WHITE)
    for dot_x in [logo_x + 5, logo_x + 11, logo_x + 17]:
        pdf.ellipse(dot_x, dot_y, 2.5, 2.5, style="F")

    # Brand text — "Dolphin" + "Buddy"
    pdf.set_xy(logo_x + logo_w + 4, 9)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*_EMERALD)
    pdf.cell(22, 7, "Dolphin", ln=0)
    pdf.set_text_color(*_WHITE)
    pdf.cell(18, 7, " Buddy", ln=0)

    # Tagline
    pdf.set_xy(logo_x + logo_w + 4, 19)
    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_text_color(*_DIM)
    pdf.cell(80, 5, "AI Insurance Support")

    # "OFFICIAL GUIDE" badge — emerald pill top-right
    badge_w, badge_h = 38, 10
    bx = pdf.w - badge_w - 8
    by = (hdr_h - badge_h) / 2
    pdf.set_fill_color(*_EMERALD)
    pdf.rect(bx, by, badge_w, badge_h, style="F")
    pdf.set_xy(bx, by + 1.5)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_text_color(*_WHITE)
    pdf.cell(badge_w, 7, "OFFICIAL GUIDE", align="C")

    # ── Title block ───────────────────────────────────────────────────────────
    pdf.set_y(hdr_h + 12)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*_TEXT)
    pdf.multi_cell(pw, 12, _safe(title), align="L")

    # Emerald underline beneath title
    ul_y = pdf.get_y() + 3
    pdf.set_draw_color(*_EMERALD)
    pdf.set_line_width(2.5)
    pdf.line(pdf.l_margin, ul_y, pdf.l_margin + 55, ul_y)
    # Lighter continuation
    pdf.set_draw_color(*_EMERALD_LIGHT)
    pdf.set_line_width(2.5)
    pdf.line(pdf.l_margin + 57, ul_y, pdf.l_margin + 70, ul_y)

    pdf.set_y(ul_y + 10)

    # ── Sections ──────────────────────────────────────────────────────────────
    for section in sections:
        heading = _safe(section["heading"])
        h_y = pdf.get_y()
        card_h = 12

        # White card for heading
        pdf.set_fill_color(*_WHITE)
        pdf.set_draw_color(*_BORDER)
        pdf.set_line_width(0.25)
        pdf.rect(pdf.l_margin - 2, h_y, pw + 4, card_h, style="FD")

        # Navy left accent pill
        pdf.set_fill_color(*_NAVY)
        pdf.rect(pdf.l_margin - 2, h_y, 4, card_h, style="F")

        # Emerald dot on left accent
        pdf.set_fill_color(*_EMERALD)
        pdf.ellipse(pdf.l_margin - 2, h_y + card_h / 2 - 1.5, 4, 4, style="F")

        pdf.set_xy(pdf.l_margin + 6, h_y + 2.5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_NAVY)
        pdf.cell(pw - 10, 7, heading)

        pdf.set_y(h_y + card_h + 5)

        # Section body lines
        for line in section["lines"]:
            safe_line = _safe(line)
            is_bullet = safe_line.startswith(("-", "*"))

            if is_bullet:
                # Emerald bullet dot
                dot_x = pdf.l_margin + 4
                dot_y = pdf.get_y() + 3.2
                pdf.set_fill_color(*_EMERALD)
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

    # Emerald-light tint card
    pdf.set_fill_color(*_EMERALD_LIGHT)
    pdf.set_draw_color(*_BORDER)
    pdf.set_line_width(0.25)
    pdf.rect(pdf.l_margin - 2, disc_y, pw + 4, disc_h, style="FD")

    # Emerald left stripe on disclaimer
    pdf.set_fill_color(*_EMERALD)
    pdf.rect(pdf.l_margin - 2, disc_y, 3, disc_h, style="F")

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
        "filename": filename,
        "version": version,
        "instruction": f"Tell the user their '{guide['title'].replace(chr(10), ' ')}' guide is ready and attached to this message.",
    }


async def generate_booking_confirmation_pdf(
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
    booking_ref: str = "",
    additional_details: str = "",
) -> dict:
    """
    Generates a policy booking confirmation PDF after a travel policy has been booked.
    Call this immediately after confirming a booking — DO NOT call it before the booking
    is confirmed or while still collecting information.

    Args:
        policy_name:        Name of the booked policy (e.g. "Tata AIG Travel Guard Gold").
        insurer:            Insurer/company name (e.g. "Tata AIG").
        destination:        Travel destination (e.g. "Dubai, UAE").
        travel_dates:       Travel dates as a string (e.g. "15 Aug 2026 – 18 Aug 2026").
        num_adults:         Number of adult travellers.
        num_children:       Number of child travellers.
        traveller_ages:     Ages of travellers as a string (e.g. "35, 32").
        sum_insured:        Coverage amount (e.g. "$50,000" or "50 Lakh").
        premium:            Final premium amount (e.g. "₹1,200").
        tool_context:       ADK tool context for saving the artifact.
        booking_ref:        Booking or reference number if available (optional).
        additional_details: Any extra notes or conditions collected during booking (optional).

    Returns:
        dict with status and filename.
    """
    sections = [
        {
            "heading": "Booking Summary",
            "lines": [
                f"- Policy: {policy_name}",
                f"- Insurer: {insurer}",
                *([ f"- Booking Reference: {booking_ref}"] if booking_ref else []),
            ],
        },
        {
            "heading": "Trip Details",
            "lines": [
                f"- Destination: {destination}",
                f"- Travel Dates: {travel_dates}",
                f"- Adults: {num_adults}",
                f"- Children: {num_children}",
                f"- Traveller Ages: {traveller_ages}",
            ],
        },
        {
            "heading": "Coverage & Premium",
            "lines": [
                f"- Sum Insured: {sum_insured}",
                f"- Premium Paid: {premium}",
            ],
        },
        {
            "heading": "Next Steps",
            "lines": [
                "- Share Passport copies (front + back) for KYC.",
                "- Share PAN card or Aadhaar for identity verification.",
                "- For any claims or support, reach out with your policy number.",
            ],
        },
        *(
            [{
                "heading": "Additional Notes",
                "lines": [additional_details],
            }] if additional_details else []
        ),
    ]

    pdf_bytes = _build_pdf("Policy Booking\nConfirmation", sections)

    artifact = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    safe_name = policy_name.lower().replace(" ", "_")[:30]
    filename = f"booking_confirmation_{safe_name}.pdf"
    version = await tool_context.save_artifact(filename=filename, artifact=artifact)

    return {
        "status": "success",
        "filename": filename,
        "version": version,
    }


async def generate_quotation_comparison_pdf(
    policies: list[dict],
    destination: str,
    travel_dates: str,
    num_adults: int,
    num_children: int,
    traveller_ages: str,
    tool_context: ToolContext,
) -> dict:
    """
    Generates a policy comparison PDF for quotations showing multiple policy options side-by-side.
    Use this when the user wants to compare policies or needs a quotation PDF.

    Args:
        policies:         List of policy dicts. Each should have: name, insurer, premium, sum_insured, highlights (list)
        destination:      Travel destination
        travel_dates:     Travel dates string
        num_adults:       Number of adults
        num_children:     Number of children
        traveller_ages:   Ages as string
        tool_context:     ADK tool context

    Returns:
        dict with status and filename
    """
    sections = [
        {
            "heading": "Trip Details",
            "lines": [
                f"- Destination: {destination}",
                f"- Travel Dates: {travel_dates}",
                f"- Travellers: {num_adults} adults, {num_children} children",
                f"- Ages: {traveller_ages}",
            ],
        },
    ]

    # Add each policy as a section
    for i, policy in enumerate(policies, 1):
        name = policy.get("name", "Policy")
        insurer = policy.get("insurer", "")
        premium = policy.get("premium", "")
        sum_insured = policy.get("sum_insured", "")
        highlights = policy.get("highlights", [])

        lines = []
        if insurer:
            lines.append(f"- Insurer: {insurer}")
        if premium:
            lines.append(f"- Premium: ₹{premium}")
        if sum_insured:
            lines.append(f"- Coverage: {sum_insured}")

        # Add highlights as bullet points
        if highlights:
            lines.append("Key Benefits:")
            for h in highlights:
                lines.append(f"  * {h}")

        sections.append({
            "heading": f"Option {i}: {name}",
            "lines": lines,
        })

    # Add disclaimer
    sections.append({
        "heading": "Important Notes",
        "lines": [
            "- All premiums are estimates and subject to insurer confirmation.",
            "- Final pricing may vary based on additional underwriting details.",
            "- Please review policy documents for full coverage details and exclusions.",
        ],
    })

    pdf_bytes = _build_pdf("Travel Insurance\nQuotation", sections)

    artifact = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    filename = f"quotation_comparison_{destination.lower().replace(' ', '_')[:20]}.pdf"
    version = await tool_context.save_artifact(filename=filename, artifact=artifact)

    return {
        "status": "success",
        "filename": filename,
        "version": version,
        "instruction": "Tell the user their quotation comparison PDF is ready and attached.",
    }
