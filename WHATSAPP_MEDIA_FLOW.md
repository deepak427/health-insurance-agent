# WhatsApp Media Processing Flow

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER SENDS DOCUMENT                              │
│                    (Passport, Aadhaar, Policy PDF)                       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    WHATSAPP CLOUD API (Meta)                             │
│  • Receives media message                                                │
│  • Generates media_id                                                    │
│  • Forwards to webhook                                                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    WEBHOOK RECEIVES MESSAGE                              │
│  File: hip/whatsapp/webhook.py                                           │
│  Function: _process_message()                                            │
│                                                                           │
│  Actions:                                                                │
│  ✓ Extract media_id, mime_type, filename                                │
│  ✓ Check for caption                                                     │
│  ✓ Call _download_and_save_media()                                      │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DOWNLOAD MEDIA FROM META                              │
│  Function: _download_and_save_media()                                    │
│                                                                           │
│  Step 1: Get Media URL                                                   │
│  GET https://graph.facebook.com/v19.0/{media_id}                         │
│  → Returns: { "url": "https://..." }                                     │
│                                                                           │
│  Step 2: Download File                                                   │
│  GET {download_url} with Authorization header                            │
│  → Returns: Binary file data                                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SAVE AS ARTIFACT                                      │
│  • Generate filename (if not provided)                                   │
│  • Get user_id and session_id from contact                               │
│  • Save to ADK artifact service                                          │
│  • Path: .adk/artifacts/apps/my_agent/users/{user_id}/sessions/{...}    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AUTO-GENERATE PROMPT                                  │
│                                                                           │
│  IF caption exists:                                                      │
│    Use caption as prompt                                                 │
│  ELSE IF image file:                                                     │
│    "I uploaded {filename}. Please extract traveler details."             │
│  ELSE IF PDF file:                                                       │
│    "I uploaded {filename}. Please analyze this insurance document."      │
│  ELSE:                                                                   │
│    "I uploaded {filename}. Please review this document."                 │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SEND TO AI AGENT                                      │
│  • Create/ensure ADK session exists                                      │
│  • POST to /run_sse with auto-generated prompt                           │
│  • Agent receives message with artifact context                          │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AGENT PROCESSES REQUEST                               │
│  File: hip/my_agent/agent.py                                             │
│  Tools: extract_traveler_details_from_document()                         │
│         analyze_insurance_document()                                     │
│                                                                           │
│  Actions:                                                                │
│  1. Loads artifact using tool_context.load_artifact(filename)            │
│  2. Sends to Gemini Vision API for analysis                              │
│  3. Extracts structured data (name, DOB, document #, etc.)               │
│  4. Returns formatted response                                           │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    FORMAT RESPONSE FOR WHATSAPP                          │
│  Function: format_for_whatsapp()                                         │
│  • Strips markdown                                                       │
│  • Converts cards to plain text                                          │
│  • Keeps WhatsApp-safe formatting (*bold*, _italic_)                     │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SEND BACK TO USER                                     │
│  • Send text response via Meta Graph API                                 │
│  • If PDF artifacts in response, send as WhatsApp documents              │
│  • Save message to database for UI display                               │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    USER RECEIVES RESPONSE                                │
│  "Full Name: John Smith                                                  │
│   Date of Birth: 15 March 1985                                           │
│   Passport Number: AB1234567                                             │
│   Nationality: Indian                                                    │
│                                                                           │
│   Is this correct? I can now use these details for your booking."        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Functions

### 1. `_process_message(msg, contact_names)`
**Location**: `hip/whatsapp/webhook.py`
**Purpose**: Main message handler
**Key Logic**:
```python
if msg_type in ("image", "document"):
    media_id = msg.get(msg_type, {}).get("id", "")
    if media_id:
        uploaded_filename = await _download_and_save_media(...)
        if not caption:
            # Auto-generate appropriate prompt
            text = f"I uploaded {filename}. Please extract..."
```

### 2. `_download_and_save_media(media_id, phone, ...)`
**Location**: `hip/whatsapp/webhook.py`
**Purpose**: Downloads media from Meta and saves as artifact
**Key Steps**:
```python
1. GET media info from Meta API → get download URL
2. GET actual file from download URL
3. Generate filename if not provided
4. Get user_id/session_id from contact
5. Save to artifact service
6. Return filename
```

### 3. `extract_traveler_details_from_document(filename, tool_context)`
**Location**: `hip/my_agent/tools/documents.py`
**Purpose**: Extract structured data from ID documents
**Key Logic**:
```python
1. Load artifact by filename
2. Send to Gemini Vision API with extraction prompt
3. Parse JSON response with traveler details
4. Return structured data
```

### 4. `analyze_insurance_document(filename, tool_context)`
**Location**: `hip/my_agent/tools/documents.py`
**Purpose**: Analyze policy documents
**Key Logic**:
```python
1. Load artifact by filename
2. Send to Gemini Vision API for policy analysis
3. Extract coverage, premium, exclusions
4. Return summary
```

## Data Flow Example

### Example: Passport Upload

```
Input:
┌──────────────────────────────────┐
│  WhatsApp Message                │
│  • type: "image"                 │
│  • media_id: "abc123..."         │
│  • mime_type: "image/jpeg"       │
│  • caption: null                 │
└──────────────────────────────────┘

Processing:
1. Download: GET https://graph.facebook.com/.../abc123
   → Binary JPEG data

2. Save: .adk/artifacts/.../whatsapp_919876543210_20241215.jpg

3. Auto-prompt: "I uploaded whatsapp_919876543210_20241215.jpg. 
                  Please extract traveler details from this document."

4. Agent calls: extract_traveler_details_from_document(
                  "whatsapp_919876543210_20241215.jpg"
                )

5. Gemini Vision extracts:
   {
     "full_name": "SMITH, JOHN ROBERT",
     "date_of_birth": "15 MAR 1985",
     "passport_number": "AB1234567",
     "nationality": "INDIAN",
     "issue_date": "12 JAN 2020",
     "expiry_date": "11 JAN 2030"
   }

Output:
┌──────────────────────────────────┐
│  WhatsApp Reply                  │
│                                  │
│  Full Name: John Robert Smith    │
│  Date of Birth: 15 March 1985    │
│  Passport Number: AB1234567      │
│  Nationality: Indian             │
│  Valid Until: 11 Jan 2030        │
│                                  │
│  Is this correct? I can now use  │
│  these details for your booking. │
└──────────────────────────────────┘
```

## Error Handling Flow

```
Media Upload Attempt
        │
        ▼
    media_id present?
    ├─ NO → "[Document received without media ID]"
    │
    └─ YES → Download from Meta API
              │
              ▼
          Download successful?
          ├─ NO → "[Document received but couldn't be downloaded]"
          │
          └─ YES → Save as artifact
                    │
                    ▼
                Save successful?
                ├─ NO → "[Document received but processing failed]"
                │
                └─ YES → Generate auto-prompt
                          │
                          ▼
                      Send to agent
                          │
                          ▼
                      Agent processes
                          │
                          ▼
                      ✓ Success!
```

## Performance Metrics

| Step | Time | Notes |
|------|------|-------|
| Media download from Meta | 1-2s | Depends on file size |
| Save to artifact storage | <0.5s | Local disk write |
| Agent processing | 2-5s | Gemini Vision API call |
| Total response time | 3-8s | Acceptable for WhatsApp UX |

## Capacity Limits

| Resource | Limit | Source |
|----------|-------|--------|
| Image size | 5 MB | WhatsApp |
| PDF size | 100 MB | WhatsApp |
| Media URL validity | 1 hour | Meta API |
| API rate limit | 1000 req/day | Meta (free tier) |
| Gemini Vision calls | Per quota | Google Cloud |

---

**Last Updated**: December 2024
