from .faq import get_insurance_faq
from .claims import get_claim_filing_steps
from .premium import estimate_premium
from .documents import analyze_insurance_document, extract_traveler_details_from_document
from .pdf_generator import generate_booking_confirmation_pdf, generate_quotation_comparison_pdf
from .booking import save_booking, get_booking_details, update_booking_details, get_recent_bookings, get_my_wallet_balance
from .addons import get_available_addons, apply_addon_to_booking
from .vas import get_available_vas, apply_vas_to_booking
