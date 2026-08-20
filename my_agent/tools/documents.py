from google.adk.tools import ToolContext
from google.genai import types as genai_types


async def analyze_insurance_document(filename: str, tool_context: ToolContext) -> dict:
    """
    Loads and analyzes an insurance document (PDF or image) uploaded as an artifact.
    Extracts key information like coverage details, exclusions, premiums, and dates.

    Args:
        filename (str): Name of the uploaded document artifact to analyze.

    Returns:
        dict: Document metadata and content ready for analysis.
    """
    artifact = await tool_context.load_artifact(filename=filename)

    if not artifact:
        return {
            "status": "error",
            "message": f"Document '{filename}' not found. Please upload it first.",
        }

    inline = artifact.inline_data
    if not inline or not inline.data:
        return {"status": "error", "message": "Document appears to be empty."}

    return {
        "status": "success",
        "filename": filename,
        "mime_type": inline.mime_type,
        "message": "Document loaded. Analyze its contents for coverage, exclusions, premiums, and key dates.",
        "artifact": artifact,
    }


async def extract_traveler_details_from_document(filename: str, tool_context: ToolContext) -> dict:
    """
    Extracts traveler personal details from uploaded identity documents (Passport, Aadhaar, PAN card, etc.).
    Use this when the user uploads a document and you need to extract booking details like name, age,
    address, date of birth, document numbers, etc.

    The model will analyze the document and extract structured information that can be used for booking.

    Args:
        filename (str): Name of the uploaded document artifact (image or PDF).

    Returns:
        dict: Contains the document artifact for model analysis and instructions.
    """
    artifact = await tool_context.load_artifact(filename=filename)

    if not artifact:
        return {
            "status": "error",
            "message": f"Document '{filename}' not found. Please upload it first.",
        }

    inline = artifact.inline_data
    if not inline or not inline.data:
        return {"status": "error", "message": "Document appears to be empty."}

    return {
        "status": "success",
        "filename": filename,
        "mime_type": inline.mime_type,
        "message": "Document loaded. Extract traveler details: full name, date of birth, age, gender, address, document number, document type. Format the extracted details clearly.",
        "artifact": artifact,
    }
