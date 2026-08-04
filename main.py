"""
Insurance Agent API Server
--------------------------
Local dev  : python main.py
AWS EC2    : set ARTIFACT_SERVICE_URI=s3://bucket + AWS_REGION for S3
             set SESSION_SERVICE_URI=postgresql+asyncpg://... for multi-instance
"""
import base64
import os
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.service_registry import get_service_registry
from google.adk.cli.utils.service_factory import create_artifact_service_from_options
from data.store import load, save, FILES
from data.bookings import get_booking, create_booking

load_dotenv()
# Also load agent-level env so BACKEND_BASE_URL / AGENT_JWT_TOKEN are available
_agent_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_agent", ".env")
load_dotenv(_agent_env, override=False)

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
    "*",
]

# ── S3 support ─────────────────────────────────────────────────────────────────
def _s3_artifact_factory(uri: str, **_):
    from urllib.parse import urlparse
    from services.s3_artifact_service import S3ArtifactService
    bucket = urlparse(uri).netloc
    region = os.environ.get("AWS_REGION", "us-east-1")
    print(f"[artifacts] S3 — bucket={bucket} region={region}")
    return S3ArtifactService(bucket_name=bucket, region_name=region)

get_service_registry().register_artifact_service("s3", _s3_artifact_factory)
# ───────────────────────────────────────────────────────────────────────────────

SESSION_SERVICE_URI = os.environ.get("SESSION_SERVICE_URI", "sqlite+aiosqlite:///./sessions.db")
ARTIFACT_SERVICE_URI = os.environ.get("ARTIFACT_SERVICE_URI", None)

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_SERVICE_URI,
    artifact_service_uri=ARTIFACT_SERVICE_URI,
    use_local_storage=True,
    allow_origins=ALLOWED_ORIGINS,
    web=False,
)

# One shared artifact service instance for the download endpoint
_artifact_svc = create_artifact_service_from_options(
    base_dir=AGENT_DIR,
    artifact_service_uri=ARTIFACT_SERVICE_URI,
    use_local_storage=True,
)


@app.get("/health")
def health():
    return {"status": "ok"}


# ── hip-backend proxy endpoints ────────────────────────────────────────────────
_HIP_BACKEND = os.environ.get("BACKEND_BASE_URL", "http://localhost:5000")
_HIP_JWT = os.environ.get("AGENT_JWT_TOKEN", "")

def _hip_headers():
    return {
        "Content-Type": "application/json",
        "Cookie": f"Authorization={_HIP_JWT}",
    }


@app.get("/policies", summary="Proxy — list all available health policies from hip-backend")
def list_policies():
    import requests as _req
    try:
        res = _req.get(f"{_HIP_BACKEND}/policy", headers=_hip_headers(), timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"hip-backend unreachable: {e}")


@app.get("/companies", summary="Proxy — list all insurance companies from hip-backend")
def list_companies():
    import requests as _req
    try:
        res = _req.get(f"{_HIP_BACKEND}/company", headers=_hip_headers(), timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"hip-backend unreachable: {e}")
# ──────────────────────────────────────────────────────────────────────────────


# ── Dynamic data endpoints ─────────────────────────────────────────────────────
VALID_KEYS = list(FILES.keys())  # ["faqs", "claims", "premium_config"]

@app.get("/data/{key}", summary="Get agent data (faqs | claims | premium_config)")
def get_data(key: str):
    if key not in VALID_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{key}'. Valid: {VALID_KEYS}")
    return load(key)


@app.put("/data/{key}", summary="Update agent data (faqs | claims | premium_config)")
async def put_data(key: str, request: Request):
    if key not in VALID_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown key '{key}'. Valid: {VALID_KEYS}")
    body = await request.json()
    save(key, body)
    return {"status": "saved", "key": key}
# ──────────────────────────────────────────────────────────────────────────────


@app.get(
    "/download/{app_name}/{user_id}/{session_id}/{filename:path}",
    summary="Download an artifact as a real file (PDF, image, etc.)",
)
async def download_artifact(
    app_name: str,
    user_id: str,
    session_id: str,
    filename: str,
    version: int = None,
):
    artifact = await _artifact_svc.load_artifact(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        version=version,
    )

    if not artifact or not artifact.inline_data:
        raise HTTPException(status_code=404, detail=f"'{filename}' not found")

    inline = artifact.inline_data
    raw = bytes(inline.data) if isinstance(inline.data, (bytes, bytearray)) else base64.b64decode(inline.data)
    mime = inline.mime_type or "application/octet-stream"

    return Response(
        content=raw,
        media_type=mime,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )


# ── Bookings API ───────────────────────────────────────────────────────────────
@app.get("/bookings/{ref_number}", summary="Get booking details by reference number")
def get_booking_endpoint(ref_number: str):
    booking = get_booking(ref_number)
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {ref_number} not found")
    return booking