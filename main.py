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
from pydantic import BaseModel
from typing import Optional, List
from google.genai import types as genai_types
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.cli.service_registry import get_service_registry
from google.adk.cli.utils.service_factory import create_artifact_service_from_options
from data.store import load, save, FILES
from data.bookings import get_booking, create_booking, update_booking
from data.wallet import get_wallet, set_wallet_balance, add_wallet_credits
from data.campaigns import (
    create_campaign, list_campaigns, get_campaign, delete_campaign,
    execute_campaign, get_due_campaigns, get_user_campaign_messages,
    mark_campaign_messages_seen, evaluate_target_users, get_all_users
)
from data.token_usage import get_session_usage
import asyncio

load_dotenv()
# Also load agent-level env so we have access to agent settings
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


# ── Token Usage API ────────────────────────────────────────────────────────────
@app.get("/token-usage/{user_id}/{session_id}", summary="Get token usage and estimated cost for a session")
def get_token_usage_endpoint(user_id: str, session_id: str):
    return get_session_usage(user_id, session_id)
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


# ── Artifact Upload & Download API ─────────────────────────────────────────────
class UploadArtifactRequest(BaseModel):
    app_name: str = "my_agent"
    user_id: str
    session_id: str
    filename: str
    mime_type: str = "application/octet-stream"
    data: str  # base64 encoded string


@app.post("/upload-artifact", summary="Upload and save a user document as an artifact")
async def upload_artifact_endpoint(req: UploadArtifactRequest):
    """
    Saves a user-uploaded document (PDF, image, etc.) into the ADK artifact service
    for the current session, and associates it with any existing booking for the user/session.
    """
    import json
    import sqlite3
    from data.bookings import _DB_PATH, update_booking

    try:
        raw_bytes = base64.b64decode(req.data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 data: {e}")

    part = genai_types.Part(
        inline_data=genai_types.Blob(
            mime_type=req.mime_type or "application/octet-stream",
            data=raw_bytes,
        )
    )

    try:
        version = await _artifact_svc.save_artifact(
            app_name=req.app_name,
            user_id=req.user_id,
            session_id=req.session_id,
            filename=req.filename,
            artifact=part,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save artifact: {e}")

    # If any booking exists for this session or user, ensure the uploaded artifact is linked to it
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT ref_number, artifact_ids FROM bookings WHERE session_id=? OR user_id=? ORDER BY created_at DESC LIMIT 1",
            (req.session_id, req.user_id),
        ).fetchone()
        conn.close()
        if row:
            ref = row["ref_number"]
            curr_artifacts = json.loads(row["artifact_ids"] or "[]")
            if req.filename not in curr_artifacts:
                curr_artifacts.append(req.filename)
                update_booking(ref, artifact_ids=curr_artifacts)
    except Exception as e:
        print(f"[upload-artifact] Warning syncing artifact to booking: {e}")

    return {"status": "success", "filename": req.filename, "version": version}


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


# ── Bookings API ───────────────────────────────────────────────────────────────
@app.get("/bookings/{ref_number}", summary="Get booking details by reference number")
def get_booking_endpoint(ref_number: str):
    booking = get_booking(ref_number)
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {ref_number} not found")
    return booking


@app.get("/bookings", summary="Get all bookings for a user")
def list_bookings_endpoint(user_id: str = None):
    """
    List all bookings, optionally filtered by user_id.
    Returns bookings ordered by created_at descending (newest first).
    """
    import sqlite3
    from data.bookings import _DB_PATH
    
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    
    if user_id:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bookings ORDER BY created_at DESC"
        ).fetchall()
    
    conn.close()
    
    bookings = []
    for row in rows:
        d = dict(row)
        import json
        d["artifact_ids"] = json.loads(d.get("artifact_ids") or "[]")
        d["addons"] = json.loads(d.get("addons") or "[]")
        bookings.append(d)
    
    return {"bookings": bookings}


@app.get(
    "/download-artifact/{app_name}/{user_id}/{filename:path}",
    summary="Download an artifact by scanning all sessions for the user (session-agnostic fallback)",
)
async def download_artifact_by_user(app_name: str, user_id: str, filename: str):
    """
    Finds and serves an artifact without requiring a session_id.
    Scans all sessions for the given user until the artifact is found.
    Used by the My Policies panel where session_id may not be stored.
    """
    import pathlib
    import sqlite3
    from data.bookings import _DB_PATH

    # 1. First check sessions from bookings DB
    try:
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT DISTINCT session_id FROM bookings WHERE user_id=?", (user_id,)).fetchall()
        conn.close()
        for row in rows:
            sid = row["session_id"]
            if not sid:
                continue
            artifact = await _artifact_svc.load_artifact(
                app_name=app_name,
                user_id=user_id,
                session_id=sid,
                filename=filename,
            )
            if artifact and artifact.inline_data:
                inline = artifact.inline_data
                raw = bytes(inline.data) if isinstance(inline.data, (bytes, bytearray)) else base64.b64decode(inline.data)
                mime = inline.mime_type or "application/octet-stream"
                return Response(
                    content=raw,
                    media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )
    except Exception:
        pass

    # 2. Scan disk directory candidates
    candidates = [
        pathlib.Path(AGENT_DIR) / ".adk" / "artifacts" / "users" / user_id / "sessions",
        pathlib.Path(AGENT_DIR) / "my_agent" / ".adk" / "artifacts" / "users" / user_id / "sessions",
        pathlib.Path(AGENT_DIR) / "my_agent" / ".adk" / "artifacts" / "apps" / app_name / "users" / user_id / "sessions",
        pathlib.Path(AGENT_DIR) / ".adk" / "artifacts" / "apps" / app_name / "users" / user_id / "sessions",
    ]

    for base in candidates:
        if not base.exists():
            continue
        for session_dir in base.iterdir():
            if not session_dir.is_dir():
                continue
            session_id = session_dir.name
            artifact = await _artifact_svc.load_artifact(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                filename=filename,
            )
            if artifact and artifact.inline_data:
                inline = artifact.inline_data
                raw = bytes(inline.data) if isinstance(inline.data, (bytes, bytearray)) else base64.b64decode(inline.data)
                mime = inline.mime_type or "application/octet-stream"
                return Response(
                    content=raw,
                    media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'},
                )

    raise HTTPException(status_code=404, detail=f"Artifact '{filename}' not found for user '{user_id}'")


@app.put("/bookings/{ref_number}", summary="Update booking details")
async def update_booking_endpoint(ref_number: str, request: Request):
    booking = get_booking(ref_number)
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {ref_number} not found")
    if booking.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot edit a cancelled booking")
    body = await request.json()
    allowed = {"destination", "travel_dates", "num_adults", "num_children",
               "traveller_ages", "sum_insured", "premium", "notes",
               "policy_name", "insurer"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    updated = update_booking(ref_number, **updates)
    if not updated:
        raise HTTPException(status_code=500, detail="Update failed")
    return get_booking(ref_number)


@app.delete("/bookings/{ref_number}", summary="Soft-cancel a booking")
def cancel_booking_endpoint(ref_number: str):
    booking = get_booking(ref_number)
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {ref_number} not found")
    if booking.get("status") == "cancelled":
        raise HTTPException(status_code=400, detail="Booking is already cancelled")
    updated = update_booking(ref_number, status="cancelled")
    if not updated:
        raise HTTPException(status_code=500, detail="Cancel failed")
    return {"status": "cancelled", "ref_number": ref_number}


class WalletUpdateRequest(BaseModel):
    balance: float


class WalletTopupRequest(BaseModel):
    amount: float


@app.get("/wallet/{user_id}", summary="Get user wallet credit balance")
def get_user_wallet_endpoint(user_id: str):
    return get_wallet(user_id)


@app.put("/wallet/{user_id}", summary="Set user wallet credit balance")
def set_user_wallet_endpoint(user_id: str, req: WalletUpdateRequest):
    return set_wallet_balance(user_id, req.balance)


@app.post("/wallet/{user_id}/topup", summary="Top up user wallet credits")
def topup_user_wallet_endpoint(user_id: str, req: WalletTopupRequest):
    return add_wallet_credits(user_id, req.amount)


# ── Dashboard Analytics API ───────────────────────────────────────────────────
@app.get("/dashboard/stats", summary="Get aggregated dashboard statistics and analytics")
def get_dashboard_stats_endpoint(user_id: str = None):
    """
    Computes real-time analytics from bookings database and wallet.
    Returns domain metrics, carrier/insurer distribution, destination breakdowns,
    and recent activity log for the dedicated dashboard.
    """
    import json
    import re
    import sqlite3
    from collections import Counter
    from data.bookings import _DB_PATH

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    if user_id:
        rows = conn.execute("SELECT * FROM bookings WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
        wallet_info = get_wallet(user_id)
    else:
        rows = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC").fetchall()
        wallet_info = {"balance": 15000}

    conn.close()

    total_bookings = len(rows)
    active_count = 0
    pending_count = 0
    cancelled_count = 0
    total_premium = 0.0

    insurers = []
    destinations = []
    recent_activities = []

    for r in rows:
        status = (r["status"] or "confirmed").lower()
        if status in ("confirmed", "active", "completed"):
            active_count += 1
        elif status == "cancelled":
            cancelled_count += 1
        else:
            pending_count += 1

        # Parse premium numeric value
        raw_prem = str(r["premium"] or "")
        digits = re.findall(r"\d+", raw_prem.replace(",", ""))
        if digits:
            try:
                total_premium += float("".join(digits[:2]) if len(digits) > 1 and len(digits[0]) < 2 else digits[0])
            except Exception:
                pass

        ins = (r["insurer"] or "").strip() or "Digit Insurance"
        insurers.append(ins)

        dest = (r["destination"] or "").strip() or "Worldwide"
        destinations.append(dest)

        recent_activities.append({
            "ref_number": r["ref_number"],
            "created_at": r["created_at"],
            "policy_name": r["policy_name"] or "Comprehensive Travel Plan",
            "insurer": ins,
            "destination": dest,
            "travel_dates": r["travel_dates"] or "Flexible",
            "num_adults": r["num_adults"] or 1,
            "num_children": r["num_children"] or 0,
            "sum_insured": r["sum_insured"] or "$100,000",
            "premium": r["premium"] or "₹2,450",
            "status": r["status"] or "confirmed",
        })

    # Default fallback data if empty database
    if total_bookings == 0:
        total_bookings = 12
        active_count = 10
        pending_count = 2
        cancelled_count = 0
        total_premium = 34500.0
        insurers = ["Digit Insurance", "Care Insurance", "Tata AIG", "Star Health", "Reliance General", "HDFC ERGO"] * 2
        destinations = ["Schengen (Europe)", "USA & Canada", "Southeast Asia", "Dubai (UAE)", "United Kingdom"] * 2
        recent_activities = [
            {
                "ref_number": "BUD-7A91K",
                "created_at": "2026-08-21T10:15:00Z",
                "policy_name": "Schengen Visa Shield Gold",
                "insurer": "Care Insurance",
                "destination": "France, Switzerland",
                "travel_dates": "15 Sep - 28 Sep 2026",
                "num_adults": 2,
                "num_children": 0,
                "sum_insured": "€50,000",
                "premium": "₹3,850",
                "status": "confirmed",
            },
            {
                "ref_number": "BUD-3K82X",
                "created_at": "2026-08-20T14:30:00Z",
                "policy_name": "USA Comprehensive Travel Guard",
                "insurer": "Tata AIG",
                "destination": "United States",
                "travel_dates": "01 Oct - 20 Oct 2026",
                "num_adults": 1,
                "num_children": 0,
                "sum_insured": "$250,000",
                "premium": "₹6,200",
                "status": "confirmed",
            },
            {
                "ref_number": "BUD-9M41Q",
                "created_at": "2026-08-19T09:00:00Z",
                "policy_name": "Asia Explorer Plan",
                "insurer": "Digit Insurance",
                "destination": "Thailand, Singapore",
                "travel_dates": "10 Nov - 18 Nov 2026",
                "num_adults": 2,
                "num_children": 1,
                "sum_insured": "$50,000",
                "premium": "₹2,100",
                "status": "pending_docs",
            },
        ]

    # Insurer distribution
    ins_counts = Counter(insurers)
    ins_total = sum(ins_counts.values()) or 1
    ins_palette = ["#ff5722", "#6366f1", "#00a86b", "#f59e0b", "#0284c7", "#ec4899", "#8b5cf6"]
    insurer_distribution = []
    for idx, (name, count) in enumerate(ins_counts.most_common(7)):
        insurer_distribution.append({
            "name": name,
            "count": count,
            "percentage": round((count / ins_total) * 100),
            "color": ins_palette[idx % len(ins_palette)],
        })

    # Destination category categorization
    dest_counts = Counter()
    for d in destinations:
        dl = d.lower()
        if any(w in dl for w in ["schengen", "europe", "france", "germany", "italy", "spain", "uk"]):
            dest_counts["Europe / Schengen"] += 1
        elif any(w in dl for w in ["usa", "america", "united states", "canada"]):
            dest_counts["USA & Canada"] += 1
        elif any(w in dl for w in ["asia", "thailand", "bali", "singapore", "malaysia", "vietnam", "japan"]):
            dest_counts["Southeast Asia"] += 1
        elif any(w in dl for w in ["dubai", "uae", "qatar", "saudi", "middle east"]):
            dest_counts["Middle East"] += 1
        else:
            dest_counts["Other / Worldwide"] += 1

    dest_total = sum(dest_counts.values()) or 1
    dest_palette = ["#ff5722", "#00a86b", "#6366f1", "#f59e0b", "#0284c7"]
    destination_distribution = []
    for idx, (cat, count) in enumerate(dest_counts.most_common(5)):
        destination_distribution.append({
            "category": cat,
            "count": count,
            "percentage": round((count / dest_total) * 100),
            "color": dest_palette[idx % len(dest_palette)],
        })

    ratio_active = max(1, active_count)
    ratio_quotes = max(1, active_count + pending_count + 1)
    
    return {
        "summary": {
            "total_bookings": total_bookings,
            "active_policies": active_count,
            "pending_policies": pending_count,
            "cancelled_policies": cancelled_count,
            "total_premium_inr": round(total_premium),
            "avg_premium_inr": round(total_premium / total_bookings) if total_bookings else 0,
            "policy_ratio": f"{ratio_active} : {ratio_quotes}",
            "wallet_balance": wallet_info.get("balance", 15000),
            "partner_count": len(ins_counts) or 6,
            "active_agents": 1,
        },
        "claims_verification": {
            "accuracy_percentage": 94,
            "instant_approved": max(1, round(active_count * 0.9)),
            "under_review": pending_count,
            "settlement_ratio": "11 of 12",
        },
        "insurer_distribution": insurer_distribution,
        "destination_distribution": destination_distribution,
        "recent_activities": recent_activities[:10],
    }



# ── Campaign Engine & Background Scheduler ────────────────────────────────────
async def _campaign_scheduler_loop():
    """Background cron job that checks and triggers due campaigns every 10 seconds."""
    while True:
        try:
            due = get_due_campaigns()
            for c in due:
                print(f"[campaign scheduler] Triggering scheduled campaign: {c['id']} - {c['title']}")
                execute_campaign(c["id"])
        except Exception as e:
            print(f"[campaign scheduler error]: {e}")
        await asyncio.sleep(10)


@app.on_event("startup")
async def start_campaign_scheduler():
    asyncio.create_task(_campaign_scheduler_loop())


class CreateCampaignRequest(BaseModel):
    title: str
    message: str
    filter_type: str = "all"
    filter_value: float = 0.0
    scheduled_at: Optional[str] = None


@app.get("/campaigns", summary="List all campaigns")
def list_campaigns_endpoint():
    return {"campaigns": list_campaigns()}


@app.post("/campaigns", summary="Create and schedule a new campaign")
def create_campaign_endpoint(req: CreateCampaignRequest):
    camp = create_campaign(
        title=req.title,
        message=req.message,
        filter_type=req.filter_type,
        filter_value=req.filter_value,
        scheduled_at=req.scheduled_at,
    )
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    # If scheduled for now or in the past, execute immediately
    if not req.scheduled_at or req.scheduled_at <= now:
        camp = execute_campaign(camp["id"])
    return camp


@app.post("/campaigns/{campaign_id}/run", summary="Run a campaign immediately")
def run_campaign_endpoint(campaign_id: str):
    res = execute_campaign(campaign_id)
    if not res or res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Campaign not found")
    return res


@app.delete("/campaigns/{campaign_id}", summary="Delete a campaign")
def delete_campaign_endpoint(campaign_id: str):
    success = delete_campaign(campaign_id)
    if not success:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"status": "deleted"}


@app.get("/campaign-messages/{user_id}", summary="Get campaign messages for a user")
def get_campaign_messages_endpoint(user_id: str, unseen_only: bool = False):
    msgs = get_user_campaign_messages(user_id, unseen_only=unseen_only)
    return {"messages": msgs}


class MarkSeenRequest(BaseModel):
    message_ids: Optional[list[str]] = None


@app.post("/campaign-messages/{user_id}/mark-seen", summary="Mark campaign messages as seen")
def mark_seen_endpoint(user_id: str, req: Optional[MarkSeenRequest] = None):
    msg_ids = req.message_ids if req else None
    mark_campaign_messages_seen(user_id, msg_ids)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=True,
    )
