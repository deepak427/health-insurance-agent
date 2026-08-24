import base64
import json
import os
from google import genai
from google.adk.tools import ToolContext
from google.genai import types as genai_types


async def analyze_insurance_document(filename: str, tool_context: ToolContext) -> dict:
    """
    Loads and analyzes an insurance document (PDF or image) uploaded as an artifact.
    Extracts key information like coverage details, exclusions, premiums, and dates.

    Args:
        filename (str): Name of the uploaded document artifact to analyze.

    Returns:
        dict: Document analysis and key insights.
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

    data_bytes = inline.data
    if isinstance(data_bytes, str):
        try:
            data_bytes = base64.b64decode(data_bytes)
        except Exception:
            pass

    # Extract text summary directly using genai client to avoid dumping huge binary base64 in conversation history
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        prompt = (
            "Analyze this uploaded insurance document. "
            "Extract key policy coverage amounts, deductibles, exclusions, emergency contact lines, "
            "and claim procedures. Present a concise bulleted summary."
        )
        part = genai_types.Part.from_bytes(data=data_bytes, mime_type=inline.mime_type or "application/pdf")
        response = client.models.generate_content(
            model='gemini-3.7-flash',
            contents=[part, prompt]
        )
        return {
            "status": "success",
            "filename": filename,
            "analysis": response.text.strip(),
        }
    except Exception as e:
        return {
            "status": "success",
            "filename": filename,
            "message": f"Document '{filename}' ({inline.mime_type}) loaded. Summary could not be pre-generated: {e}",
        }


async def extract_traveler_details_from_document(filename: str, tool_context: ToolContext) -> dict:
    """
    Extracts traveler personal details from uploaded identity documents (Passport, Aadhaar, PAN card, etc.).
    Use this when the user uploads a document and you need to extract booking details like name, age,
    address, date of birth, document numbers, etc.

    Args:
        filename (str): Name of the uploaded document artifact (image or PDF).

    Returns:
        dict: Extracted traveler identity information.
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

    data_bytes = inline.data
    if isinstance(data_bytes, str):
        try:
            data_bytes = base64.b64decode(data_bytes)
        except Exception:
            pass

    # Extract structured traveler details directly using genai client
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        prompt = (
            "You are an expert KYC document parser. "
            "Examine this document (Passport, Aadhaar, PAN, or Ticket). "
            "Extract all traveler information in concise JSON format: "
            "full_name, date_of_birth, age, gender, document_type, document_number, "
            "nationality, address, destination, travel_dates. "
            "Return ONLY the JSON object."
        )
        part = genai_types.Part.from_bytes(data=data_bytes, mime_type=inline.mime_type or "image/jpeg")
        response = client.models.generate_content(
            model='gemini-3.7-flash',
            contents=[part, prompt]
        )
        return {
            "status": "success",
            "filename": filename,
            "extracted_details": response.text.strip(),
        }
    except Exception as e:
        return {
            "status": "success",
            "filename": filename,
            "message": f"Document '{filename}' ({inline.mime_type}) loaded.",
            "error": str(e),
        }
