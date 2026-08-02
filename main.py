"""
Insurance Agent API Server
--------------------------
Local dev  : python main.py
             Sessions  → SQLite (sessions.db)
             Artifacts → local filesystem (managed by ADK under agents_dir)

AWS EC2    : set env vars, run the same command
             ARTIFACT_SERVICE_URI=s3://your-bucket-name
             AWS_REGION=us-east-1                         (default: us-east-1)
             SESSION_SERVICE_URI=sqlite+aiosqlite:///./sessions.db  (default)

Multi-node : SESSION_SERVICE_URI=postgresql+asyncpg://user:pass@host/db
"""
import os
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.service_registry import get_service_registry

load_dotenv()  # loads .env from the same folder as main.py

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8080",
    "*",  # lock to your domain in production
]

# ── Register S3 as a custom artifact URI scheme ────────────────────────────────
def _s3_artifact_factory(uri: str, **_) -> "S3ArtifactService":
    """Factory called by ADK when artifact_service_uri starts with s3://"""
    from urllib.parse import urlparse
    from services.s3_artifact_service import S3ArtifactService
    parsed = urlparse(uri)
    bucket = parsed.netloc          # s3://my-bucket  →  netloc = "my-bucket"
    region = os.environ.get("AWS_REGION", "us-east-1")
    print(f"[artifacts] S3 — bucket={bucket} region={region}")
    return S3ArtifactService(bucket_name=bucket, region_name=region)

get_service_registry().register_artifact_service("s3", _s3_artifact_factory)
# ───────────────────────────────────────────────────────────────────────────────

SESSION_SERVICE_URI = os.environ.get(
    "SESSION_SERVICE_URI",
    "sqlite+aiosqlite:///./sessions.db",
)

# If not set: ADK uses local filesystem storage automatically (no config needed)
ARTIFACT_SERVICE_URI = os.environ.get("ARTIFACT_SERVICE_URI", None)

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    session_service_uri=SESSION_SERVICE_URI,
    artifact_service_uri=ARTIFACT_SERVICE_URI,   # None = local fs, s3://bucket = S3
    use_local_storage=True,
    allow_origins=ALLOWED_ORIGINS,
    web=False,
)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )
