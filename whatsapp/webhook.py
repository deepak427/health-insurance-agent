"""
WhatsApp webhook — Meta Cloud API integration.

Handles:
  GET  /webhook/whatsapp  — Meta verification handshake (one-time setup)
  POST /webhook/whatsapp  — Inbound message handler

Flow for every inbound message:
  1. Parse phone + text from Meta payload
  2. Idempotency check (duplicate delivery guard)
  3. get_or_create_contact() → stable user_id + session_id
  4. Persist inbound message to whatsapp_messages
  5. If ai_muted → stop here (UI shows it, agent can reply manually)
  6. Ensure ADK session exists
  7. Call ADK agent via internal HTTP → collect full response
  8. format_for_whatsapp(response) → send text via Meta Graph API
  9. For each PDF artifact in response → send as WhatsApp document
 10. Persist outbound message (full text with card markers) for UI display

Environment variables required (add to hip/.env):
  WHATSAPP_PHONE_NUMBER_ID   — from Meta App Dashboard
  WHATSAPP_TOKEN             — permanent system user token
  WHATSAPP_VERIFY_TOKEN      — any secret string you set in Meta webhook config
"""
import os
import json
import asyncio
import httpx
import logging
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

from data.whatsapp_contacts import (
    get_or_create_contact,
    save_message,
    set_ai_muted,
    message_already_processed,
)
from whatsapp.formatter import (
    format_for_whatsapp, 
    extract_artifact_filenames,
    extract_interactive_messages,
    _build_policy_list_fallback
)

logger = logging.getLogger("whatsapp.webhook")

router = APIRouter(prefix="/api", tags=["whatsapp"])

# ── Meta Graph API constants ───────────────────────────────────────────────────
_GRAPH_URL = "https://graph.facebook.com/v19.0"
_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
_WA_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "dolphin_verify")
_CATALOG_ID = os.environ.get("WHATSAPP_CATALOG_ID", "")  # WhatsApp Product Catalog ID

# ADK app name — must match the folder name under hip/
_ADK_APP_NAME = "my_agent"
# Internal base URL for ADK REST calls (localhost, same process)
_ADK_BASE = "http://localhost:8000"

# ── Recent messages cache to prevent duplicate sends ───────────────────────────
from collections import deque
from datetime import datetime, timedelta

_recent_sends = deque(maxlen=100)  # Store last 100 sent messages

def _is_duplicate_send(phone: str, text: str) -> bool:
    """Check if we recently sent the exact same message to this phone number."""
    now = datetime.now()
    # Clean up old entries (older than 60 seconds)
    while _recent_sends and (now - _recent_sends[0][2]) > timedelta(seconds=60):
        _recent_sends.popleft()
    
    # Check if this exact message was sent recently
    for sent_phone, sent_text, sent_time in _recent_sends:
        if sent_phone == phone and sent_text == text:
            if (now - sent_time) < timedelta(seconds=10):  # Within 10 seconds
                return True
    return False

def _mark_as_sent(phone: str, text: str):
    """Mark a message as sent to prevent duplicates."""
    _recent_sends.append((phone, text, datetime.now()))


# ── Verification handshake (GET) — kept for direct Meta fallback ──────────────
@router.get("/whatsapp/webhook", include_in_schema=False)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Not used when forwarding via Whatsbyte CRM — kept for direct Meta fallback."""
    if hub_mode == "subscribe" and hub_verify_token == _VERIFY_TOKEN:
        logger.info("[whatsapp] Webhook verified by Meta.")
        return PlainTextResponse(hub_challenge or "")
    logger.warning("[whatsapp] Webhook verification failed — token mismatch.")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


# ── Inbound message handler (POST) ────────────────────────────────────────────
@router.post("/whatsapp/webhook", status_code=200)
async def receive_whatsapp(request: Request):
    """
    Receives forwarded Meta webhook payloads from Whatsbyte CRM.
    Always returns 200 immediately — processing is fire-and-forget.
    """
    try:
        body = await request.json()
        logger.info(f"[whatsapp] Webhook received: {len(body.get('entry', []))} entries")
    except Exception as e:
        logger.error(f"[whatsapp] Failed to parse webhook body: {e}")
        return {"status": "ok"}

    asyncio.create_task(_handle_payload(body))
    return {"status": "ok"}


async def _handle_payload(body: dict):
    """Process a single Meta webhook payload (may contain multiple messages)."""
    try:
        entry = body.get("entry", [])
        for e in entry:
            for change in e.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                # Build a phone → display_name map from the contacts block
                contact_names = {}
                for c in contacts:
                    wa_id = c.get("wa_id", "")
                    name = c.get("profile", {}).get("name", "")
                    if wa_id:
                        contact_names[wa_id] = name

                for msg in messages:
                    await _process_message(msg, contact_names)
    except Exception as e:
        logger.error(f"[whatsapp] Error processing payload: {e}", exc_info=True)


async def _process_message(msg: dict, contact_names: dict):
    """Handle a single inbound WhatsApp message object."""
    wa_message_id = msg.get("id", "")
    msg_type = msg.get("type", "")
    phone = msg.get("from", "")

    if not phone:
        return

    # ── Idempotency guard ──────────────────────────────────────────────────────
    if wa_message_id and message_already_processed(wa_message_id):
        logger.debug(f"[whatsapp] Skipping duplicate message {wa_message_id}")
        return

    # Extract text (text messages) or caption (image/doc messages)
    text = ""
    uploaded_filename = None
    uploaded_agent_prompt = None  # Separate prompt for AI when media is uploaded
    
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "").strip()
    
    elif msg_type == "interactive":
        # Handle interactive message responses (list/button clicks)
        interactive = msg.get("interactive", {})
        interactive_type = interactive.get("type", "")
        
        if interactive_type == "list_reply":
            # User selected from interactive list
            list_reply = interactive.get("list_reply", {})
            selected_id = list_reply.get("id", "")
            selected_title = list_reply.get("title", "")
            
            logger.info(f"[whatsapp] Interactive list selection: {selected_id} - {selected_title}")
            
            # Map selection to user-friendly text
            if selected_id.startswith("policy_"):
                text = f"I'd like to book {selected_title}"
            elif selected_id.startswith("addon_"):
                text = f"Add {selected_title} to my policy"
            elif selected_id.startswith("vas_"):
                text = f"I want {selected_title}"
            else:
                text = selected_title
        
        elif interactive_type == "button_reply":
            # User clicked an interactive button
            button_reply = interactive.get("button_reply", {})
            button_id = button_reply.get("id", "")
            button_title = button_reply.get("title", "")
            
            logger.info(f"[whatsapp] Interactive button click: {button_id} - {button_title}")
            
            # Map button clicks to actions
            if button_id == "confirm_booking":
                text = "Yes, confirm the booking"
            elif button_id == "modify_booking":
                text = "I want to modify the booking"
            elif button_id == "cancel_booking":
                text = "Cancel the booking"
            else:
                text = button_title
        
        else:
            logger.warning(f"[whatsapp] Unknown interactive type: {interactive_type}")
            return
    
    elif msg_type in ("image", "document"):
        # Download and save media automatically
        media_data = msg.get(msg_type, {})
        media_id = media_data.get("id", "")
        caption = media_data.get("caption", "").strip()
        mime_type = media_data.get("mime_type", "")
        filename = media_data.get("filename", "") if msg_type == "document" else ""
        
        if media_id:
            try:
                uploaded_filename = await _download_and_save_media(
                    media_id, phone, mime_type, filename, msg_type
                )
                if uploaded_filename:
                    # Create display text (what users see in UI) and agent prompt (what AI receives)
                    if caption:
                        # User provided a caption
                        display_text = f"📎 {uploaded_filename}\n{caption}"
                        agent_prompt = caption  # AI gets the caption as instruction
                    else:
                        # No caption - create appropriate display and agent instruction
                        if msg_type == "image" or mime_type.startswith("image/"):
                            display_text = f"📷 {uploaded_filename}"
                            agent_prompt = f"I uploaded {uploaded_filename}. Please extract traveler details from this document."
                        elif "pdf" in mime_type.lower() or (filename and filename.endswith(".pdf")):
                            display_text = f"📄 {uploaded_filename}"
                            agent_prompt = f"I uploaded {uploaded_filename}. Please analyze this insurance document."
                        else:
                            display_text = f"📎 {uploaded_filename}"
                            agent_prompt = f"I uploaded {uploaded_filename}. Please review this document."
                    
                    text = display_text  # Used for saving to DB (what UI shows)
                    # Store agent_prompt separately - we'll use it when calling the agent
                    uploaded_agent_prompt = agent_prompt
                    
                    logger.info(f"[whatsapp] Media saved as {uploaded_filename}, display: {display_text}")
                else:
                    text = "[Document received but couldn't be downloaded - please try again]"
                    uploaded_agent_prompt = None
            except Exception as e:
                logger.error(f"[whatsapp] Failed to download media: {e}", exc_info=True)
                text = f"[Document received but processing failed - please try again]"
        else:
            text = caption if caption else "[Document received without media ID]"
    elif msg_type in ("audio", "video"):
        text = msg.get(msg_type, {}).get("caption", "").strip()
        if not text:
            text = f"[{msg_type} messages are not supported yet]"
    elif msg_type == "interactive":
        # Button reply or list reply
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive["button_reply"].get("title", "").strip()
        elif interactive.get("type") == "list_reply":
            text = interactive["list_reply"].get("title", "").strip()
    else:
        # Sticker, location, etc. — acknowledge but don't process
        logger.info(f"[whatsapp] Unsupported message type '{msg_type}' from {phone}")
        return

    if not text:
        return

    display_name = contact_names.get(phone, "")

    # ── Lookup / create contact record ────────────────────────────────────────
    contact = get_or_create_contact(phone, display_name or None)
    user_id = contact["user_id"]
    session_id = contact["session_id"]
    name_label = contact.get("display_name") or phone

    logger.info(f"[whatsapp] Inbound from {phone} ({name_label}): {text[:80]}")

    # ── Persist inbound message ────────────────────────────────────────────────
    save_message(
        phone=phone,
        direction="inbound",
        text=text,
        sender_label=name_label,
        wa_message_id=wa_message_id,
    )

    # ── Mute check — if agent is silenced, stop here ───────────────────────────
    if contact.get("ai_muted"):
        logger.info(f"[whatsapp] AI muted for {phone} — message stored, awaiting manual reply.")
        return

    # ── Ensure ADK session exists ──────────────────────────────────────────────
    await _ensure_adk_session(user_id, session_id)

    # ── Call ADK agent and collect full response ───────────────────────────────
    # If media was uploaded, use the agent prompt instead of display text
    agent_input_text = uploaded_agent_prompt if uploaded_agent_prompt else text
    agent_response_text = await _call_agent(user_id, session_id, agent_input_text)

    if not agent_response_text:
        logger.warning(f"[whatsapp] Agent returned empty response for {phone}")
        return

    # ── Persist full response (with card markers) for UI display ──────────────
    save_message(
        phone=phone,
        direction="outbound",
        text=agent_response_text,
        sender_label="Buddy",
    )

    # ── Format and send to WhatsApp ────────────────────────────────────────────
    # Extract interactive messages (carousel/lists/buttons) or fallback to plain text
    formatted = extract_interactive_messages(agent_response_text)
    
    # Send interactive list/carousel if available (policies, addons, VAS)
    if formatted.get("interactive_list"):
        interactive_payload = formatted["interactive_list"]
        
        # Check if it's a product_list (carousel) and handle catalog ID
        if interactive_payload.get("type") == "product_list":
            if _CATALOG_ID:
                # Replace placeholder with actual catalog ID
                interactive_payload["action"]["catalog_id"] = _CATALOG_ID
                
                if not _is_duplicate_send(phone, "interactive_carousel"):
                    logger.info(f"[whatsapp] Sending product carousel to {phone}")
                    success = await _send_interactive_message(phone, interactive_payload)
                    
                    if success:
                        _mark_as_sent(phone, "interactive_carousel")
                        # Send accompanying text if any
                        if formatted.get("text"):
                            await _send_text_message(phone, formatted["text"])
                    else:
                        # Carousel failed, use fallback list
                        logger.warning(f"[whatsapp] Carousel failed, using fallback list for {phone}")
                        fallback_data = interactive_payload.get("_fallback_data", [])
                        if fallback_data:
                            fallback_list = _build_policy_list_fallback(fallback_data)
                            await _send_interactive_message(phone, fallback_list)
            else:
                # No catalog ID configured, use fallback list
                logger.info(f"[whatsapp] No catalog configured, using fallback list for {phone}")
                fallback_data = interactive_payload.get("_fallback_data", [])
                if fallback_data:
                    fallback_list = _build_policy_list_fallback(fallback_data)
                    await _send_interactive_message(phone, fallback_list)
                    if formatted.get("text"):
                        await _send_text_message(phone, formatted["text"])
        else:
            # Regular list or other interactive type
            if not _is_duplicate_send(phone, "interactive_list"):
                logger.info(f"[whatsapp] Sending interactive list to {phone}")
                await _send_interactive_message(phone, interactive_payload)
                _mark_as_sent(phone, "interactive_list")
                
                # Also send any accompanying text
                if formatted.get("text"):
                    await _send_text_message(phone, formatted["text"])
    
    # Send interactive buttons if available (confirmations)
    elif formatted.get("interactive_buttons"):
        if not _is_duplicate_send(phone, "interactive_buttons"):
            logger.info(f"[whatsapp] Sending interactive buttons to {phone}")
            await _send_interactive_message(phone, formatted["interactive_buttons"])
            _mark_as_sent(phone, "interactive_buttons")
            
            # Also send any accompanying text
            if formatted.get("text"):
                await _send_text_message(phone, formatted["text"])
    
    # Fallback to plain text
    else:
        wa_text = formatted.get("plain_text") or format_for_whatsapp(agent_response_text)
        if wa_text:
            # Check for duplicate send
            if _is_duplicate_send(phone, wa_text):
                logger.warning(f"[whatsapp] Duplicate send detected for {phone}, skipping")
                return
            
            logger.info(f"[whatsapp] Sending plain text to {phone}: {len(wa_text)} chars")
            await _send_text_message(phone, wa_text)
            _mark_as_sent(phone, wa_text)
        else:
            logger.warning(f"[whatsapp] Empty formatted text for {phone}, nothing to send")

    # ── Send any PDF artifacts as WhatsApp document messages ──────────────────
    pdf_names = extract_artifact_filenames(agent_response_text)
    for filename in pdf_names:
        await _send_pdf_artifact(phone, user_id, session_id, filename)


# ── Media download helper ──────────────────────────────────────────────────────

async def _download_and_save_media(
    media_id: str,
    phone: str,
    mime_type: str,
    filename: str,
    msg_type: str
) -> str:
    """
    Downloads media from WhatsApp Cloud API and saves it as an artifact.
    Returns the saved filename or None if failed.
    """
    if not _WA_TOKEN:
        logger.warning("[whatsapp] WHATSAPP_TOKEN not set - cannot download media")
        return None
    
    try:
        # Step 1: Get media URL from Meta Graph API
        media_url_endpoint = f"{_GRAPH_URL}/{media_id}"
        headers = {"Authorization": f"Bearer {_WA_TOKEN}"}
        
        async with httpx.AsyncClient(timeout=15) as client:
            # Get media info (URL)
            media_info_resp = await client.get(media_url_endpoint, headers=headers)
            if media_info_resp.status_code != 200:
                logger.error(f"[whatsapp] Failed to get media info: {media_info_resp.status_code}")
                return None
            
            media_info = media_info_resp.json()
            download_url = media_info.get("url")
            if not download_url:
                logger.error("[whatsapp] No download URL in media info")
                return None
            
            # Step 2: Download the actual media file
            media_resp = await client.get(download_url, headers=headers)
            if media_resp.status_code != 200:
                logger.error(f"[whatsapp] Failed to download media: {media_resp.status_code}")
                return None
            
            media_bytes = media_resp.content
            
            # Step 3: Generate a filename
            if not filename:
                # Generate filename based on type and timestamp
                import datetime
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                ext_map = {
                    "image/jpeg": "jpg",
                    "image/png": "png",
                    "application/pdf": "pdf",
                    "image/webp": "webp",
                }
                ext = ext_map.get(mime_type, msg_type)
                filename = f"whatsapp_{phone}_{ts}.{ext}"
            
            # Step 4: Save as artifact using ADK artifact service
            # We need to store it for the user's session
            contact = get_or_create_contact(phone)
            user_id = contact["user_id"]
            session_id = contact["session_id"]
            
            # Import artifact service
            from main import _artifact_svc
            import google.genai.types as types
            
            artifact = types.Part(
                inline_data=types.Blob(
                    mime_type=mime_type or "application/octet-stream",
                    data=media_bytes,
                )
            )
            
            await _artifact_svc.save_artifact(
                app_name=_ADK_APP_NAME,
                user_id=user_id,
                session_id=session_id,
                filename=filename,
                artifact=artifact,
            )
            
            logger.info(f"[whatsapp] Media saved as artifact: {filename}")
            return filename
            
    except Exception as e:
        logger.error(f"[whatsapp] Error downloading/saving media: {e}", exc_info=True)
        return None


# ── ADK session helpers ────────────────────────────────────────────────────────

async def _ensure_adk_session(user_id: str, session_id: str):
    """Create ADK session if it doesn't exist yet. 409 = already exists, that's fine."""
    url = f"{_ADK_BASE}/apps/{_ADK_APP_NAME}/users/{user_id}/sessions/{session_id}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={"state": {"user_id": user_id, "session_id": session_id}},
            )
    except Exception as e:
        logger.warning(f"[whatsapp] Session ensure warning: {e}")


async def _call_agent(user_id: str, session_id: str, text: str) -> str:
    """
    Send a message to the ADK agent via /run_sse (streaming) and collect
    the complete response text.

    We read the SSE stream locally (same server) and accumulate all text chunks.
    This mirrors exactly what the frontend does, ensuring the same agent
    behaviour, guardrails, token tracking, and tool calls all fire normally.
    """
    url = f"{_ADK_BASE}/run_sse"
    # streaming=False: ADK emits a single final content event instead of
    # incremental chunks + a final summary, which would cause the response
    # text to be accumulated twice and sent as a duplicate to WhatsApp.
    payload = {
        "appName": _ADK_APP_NAME,
        "userId": user_id,
        "sessionId": session_id,
        "newMessage": {
            "role": "user",
            "parts": [{"text": text}],
        },
        "streaming": False,
    }

    accumulated_text = ""
    accumulated_artifacts: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    logger.error(f"[whatsapp] ADK /run_sse returned {response.status_code}")
                    return ""

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    lines = buffer.split("\n")
                    buffer = lines.pop()  # keep incomplete last line

                    for line in lines:
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        # Collect text from model content
                        content = event.get("content")
                        if content and content.get("role") == "model":
                            for part in content.get("parts", []):
                                if "text" in part and part["text"]:
                                    accumulated_text += part["text"]

                        # Collect artifact filenames
                        artifact_delta = event.get("actions", {}).get("artifactDelta", {})
                        for fname in artifact_delta.keys():
                            if fname not in accumulated_artifacts:
                                accumulated_artifacts.append(fname)

    except Exception as e:
        logger.error(f"[whatsapp] Error calling ADK agent: {e}", exc_info=True)
        return ""

    # Append artifact filenames as pseudo-text so formatter can detect them
    # (extract_artifact_filenames scans for *.pdf in the full response string)
    for fname in accumulated_artifacts:
        if fname.lower().endswith(".pdf") and fname not in accumulated_text:
            accumulated_text += f"\n{fname}"

    return accumulated_text.strip()


# ── Meta Graph API senders ─────────────────────────────────────────────────────

async def _send_text_message(to: str, text: str):
    """Send a plain text message to a WhatsApp number via Meta Graph API."""
    if not _PHONE_NUMBER_ID or not _WA_TOKEN:
        logger.warning("[whatsapp] WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_TOKEN not set — skipping send.")
        return

    # WhatsApp has a 4096-char limit per message; split if needed
    chunks = _split_message(text, limit=4000)
    for chunk in chunks:
        await _post_to_graph(to, {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": chunk},
        })


async def _send_interactive_message(to: str, interactive_payload: dict) -> bool:
    """
    Send a WhatsApp Interactive Message (list, buttons, or carousel) via Meta Graph API.
    
    Args:
        to: WhatsApp phone number (with country code)
        interactive_payload: Dict with interactive message structure
            For lists: {"type": "list", "header": {...}, "body": {...}, "action": {...}}
            For buttons: {"type": "button", "body": {...}, "action": {...}}
            For carousel: {"type": "product_list", "header": {...}, "action": {"catalog_id": ...}}
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    if not _PHONE_NUMBER_ID or not _WA_TOKEN:
        logger.warning("[whatsapp] WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_TOKEN not set — skipping send.")
        return False
    
    # Remove internal fallback data before sending
    payload_to_send = {k: v for k, v in interactive_payload.items() if not k.startswith("_")}
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "interactive",
        "interactive": payload_to_send
    }
    
    return await _post_to_graph(to, payload)


async def _send_pdf_artifact(
    to: str, user_id: str, session_id: str, filename: str
):
    """
    Download a PDF artifact from local storage and send it to WhatsApp
    as a document message using a publicly accessible download URL.

    Meta requires either a hosted URL or a media upload ID.
    We use the /download endpoint (served by this same FastAPI server)
    which means the EC2 public IP must be reachable by Meta's servers.
    """
    if not _PHONE_NUMBER_ID or not _WA_TOKEN:
        return

    # Build the public download URL — relies on EC2 being publicly accessible
    # If behind a load balancer or private network, replace with your public URL
    public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not public_base:
        logger.warning("[whatsapp] PUBLIC_BASE_URL not set — cannot send PDF artifact.")
        return

    download_url = (
        f"{public_base}/download/{_ADK_APP_NAME}"
        f"/{user_id}/{session_id}/{filename}"
    )

    await _post_to_graph(to, {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "document",
        "document": {
            "link": download_url,
            "caption": filename,
            "filename": filename,
        },
    })


async def _post_to_graph(to: str, payload: dict) -> bool:
    """
    Execute a single Meta Graph API message send.
    Returns True if successful, False otherwise.
    """
    url = f"{_GRAPH_URL}/{_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {_WA_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(url, json=payload, headers=headers)
            if res.status_code not in (200, 201):
                logger.error(
                    f"[whatsapp] Graph API error {res.status_code}: {res.text[:300]}"
                )
                return False
            else:
                logger.debug(f"[whatsapp] Message sent to {to}: {res.status_code}")
                return True
    except Exception as e:
        logger.error(f"[whatsapp] Failed to post to Graph API: {e}", exc_info=True)
        return False


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Split a long message at word boundaries to stay under WhatsApp's limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Find last newline or space before limit
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = text.rfind(" ", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    return chunks


# ── Manual reply sender (called from the /whatsapp/{phone}/reply endpoint) ────

async def send_manual_reply(phone: str, text: str, agent_name: str = "Agent") -> bool:
    """
    Send a human-typed reply from the UI to a WhatsApp contact.
    Persists the outbound message and sends via Meta Graph API.
    """
    save_message(
        phone=phone,
        direction="outbound",
        text=text,
        sender_label=agent_name,
    )
    await _send_text_message(phone, text)
    return True
