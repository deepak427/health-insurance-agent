# HIP — Backend Reference

> Single source of truth for the `hip` backend (insurance support AI agent).
> Covers architecture, API contract, agent tools, deployment, and upgrade paths.
> Frontend context lives in `hip-frontend/FRONTEND_REFERENCE.md`.

---

## What is this?

An **insurance support AI agent** built with [Google ADK](https://adk.dev).
The agent answers insurance questions, explains policies, guides claim filing, estimates premiums,
and generates PDF guides — all through a REST + SSE API.

---

## Tech Stack

| Layer | What | Details |
|---|---|---|
| AI Framework | Google ADK (`google-adk`) | Multi-tool agent orchestration |
| Model | `gemini-2.5-flash` | Fast Gemini model via Vertex AI |
| API Server | FastAPI via `get_fast_api_app()` | Auto-generated REST + SSE endpoints |
| Sessions | SQLite (`session.db`) on EC2 | Conversation history persistence |
| Artifacts | Local filesystem (`my_agent/.adk/artifacts/`) | PDF storage per session |
| Runtime | Uvicorn on EC2 (systemd service) | Auto-restart on crash/reboot |

**Upgrade paths (zero code change):**
- SQLite → Postgres: set `SESSION_SERVICE_URI=postgresql+asyncpg://...`
- Local artifacts → S3: set `ARTIFACT_SERVICE_URI=s3://bucket` + `AWS_REGION`

---

## Project Structure

```
hip/
├── main.py                        ← FastAPI entrypoint, all config lives here
├── .env                           ← secrets (never committed)
├── .env.example                   ← template
├── requirements.txt
├── Dockerfile
├── services/
│   └── s3_artifact_service.py     ← custom S3 artifact backend
└── my_agent/
    ├── agent.py                   ← root ADK agent, model + tools wired here
    ├── prompt.py                  ← system prompt / agent personality
    ├── __init__.py
    └── tools/
        ├── faq.py                 ← get_insurance_faq
        ├── claims.py              ← get_claim_filing_steps
        ├── premium.py             ← estimate_premium
        ├── documents.py           ← analyze_insurance_document (reads uploaded PDFs)
        └── pdf_generator.py       ← generate_insurance_summary_pdf (creates + saves PDFs)
```

---

## Live Server

| | |
|---|---|
| Base URL | `http://43.204.143.233:8000` |
| Swagger UI | `http://43.204.143.233:8000/docs` |
| Health check | `GET /health` |

---

## API Endpoints

| Method | Path | What it does |
|---|---|---|
| `GET` | `/list-apps` | Returns `["my_agent"]` |
| `POST` | `/apps/my_agent/users/{userId}/sessions/{sessionId}` | Create session — returns `409` if already exists (safe to ignore) |
| `POST` | `/run` | Send message, get full response at once |
| `POST` | `/run_sse` | Send message, get streaming SSE response |
| `GET` | `/download/{app_name}/{userId}/{sessionId}/{filename}` | Download artifact (PDF) as binary |
| `GET` | `/apps/my_agent/users/{userId}/sessions/{sessionId}/artifacts` | List artifacts in a session |

Full schemas at `/docs`.

---

## Conversation Flow

```
1. Create session (once per conversation)
   POST /apps/my_agent/users/{userId}/sessions/{sessionId}
   → 200 OK (created) or 409 Conflict (already exists — reuse it)

2. Send message
   POST /run_sse  { streaming: true }

3. Read SSE stream
   Each line: data: { ...event... }
   Text chunks: events where content.role == "model" and content.parts[].text exists
   Artifacts:   events where actions.artifactDelta is present (can be on ANY event, not just model-role)

4. Download generated PDF
   GET /download/my_agent/{userId}/{sessionId}/{filename}
```

---

## SSE Event Shape

```jsonc
data: {
  "author": "insurance_support_agent",
  "content": {
    "role": "model",
    "parts": [{ "text": "Here is your guide..." }]
  },
  "actions": {
    // only present when a PDF artifact was saved
    "artifactDelta": { "life_insurance_guide.pdf": 0 }
  }
}
```

**Important:** `artifactDelta` can appear on tool-result events (not just model-role events).
Always scan every SSE event for `artifactDelta`, not only model-role ones.

---

## Agent Tools

| Tool function | Triggered when user says | Returns |
|---|---|---|
| `get_insurance_faq` | "What is a deductible?" | FAQ dict with definition, examples, tips |
| `get_claim_filing_steps` | "How do I file an auto claim?" | Step-by-step guide + required docs |
| `estimate_premium` | "Estimate my health premium, age 30" | Monthly/annual estimate + factors |
| `generate_insurance_summary_pdf` | "Give me a PDF guide on life insurance" | Saves PDF artifact, returns `artifactDelta` |
| `analyze_insurance_document` | Upload a PDF + "Analyze this policy" | Reads and summarizes the document |
| `LoadArtifactsTool` | (internal) | Lets agent re-read saved artifacts |

PDF guide types: `health`, `auto`, `home`, `life`, `travel`

---

## Sending a PDF for Analysis

```jsonc
POST /run
{
  "appName": "my_agent",
  "userId": "user1",
  "sessionId": "session1",
  "newMessage": {
    "role": "user",
    "parts": [
      { "text": "Analyze this insurance policy" },
      {
        "inlineData": {
          "mimeType": "application/pdf",
          "data": "<base64 encoded PDF bytes>"
        }
      }
    ]
  }
}
```

---

## Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Uvicorn port |
| `GOOGLE_API_KEY` | — | Gemini API key |
| `SESSION_SERVICE_URI` | SQLite | Swap to postgres for scale |
| `ARTIFACT_SERVICE_URI` | local filesystem | Swap to `s3://bucket` for cloud |
| `AWS_REGION` | — | Required if using S3 artifacts |

---

## Known Behaviours & Gotchas

- `POST /sessions/...` returns `409` when session already exists — this is normal, treat as success
- `artifactDelta` appears on tool events, not always on the final model-text event — check all SSE events
- Artifact filenames follow the pattern `{type}_insurance_guide.pdf` (e.g. `life_insurance_guide.pdf`)
- Sessions persist across server restarts (SQLite on disk)
- The agent may repeat the artifact filename in its text response — don't parse filenames from text, use `artifactDelta`
