from google.adk.tools import ToolContext


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
