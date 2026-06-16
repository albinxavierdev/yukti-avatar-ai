# yukti-avatar-ai

Voice assistant by Bizfy Solution (Yukti) — 3D avatar, Groq LLM, remote TTS via [bizfyvoice](https://voice.bizfylabs.com), streaming replies, SQLite chat history, and Mem0 long-term memory.

## Quick start (local)

```bash
cd yukti
bash scripts/setup_local.sh   # venv, deps, .env, assets, DB
bash scripts/run_web.sh
```

Open **http://127.0.0.1:8765**

With `AUTH_DISABLED=1` in `.env` (set by setup), you skip login and use a dev user.

## Requirements

- Python 3.12+
- `curl` (vendor download)
- Groq API key — https://console.groq.com

Optional for Google sign-in:

- Google OAuth client — redirect URI: `http://127.0.0.1:8765/auth/google/callback`

## Environment (`.env`)

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Required for chat |
| `GROQ_MODEL` | Default `llama-3.1-8b-instant` |
| `AUTH_DISABLED` | `1` = local dev without Google |
| `SECRET_KEY` | JWT cookie signing |
| `BASE_URL` | `http://127.0.0.1:8765` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Production login |
| `DATABASE_PATH` | SQLite file (default `data/yukti.db`) |
| `MEM0_DIR` | Mem0 vector store (default `data/mem0`) |
| `BIZFY_VOICE_URL` | bizfyvoice API base (default `http://127.0.0.1:8000`) |
| `BIZFY_VOICE_API_KEY` | `X-Api-Key` for `/tts` |
| `BIZFY_VOICE_SPEED` | Piper speech rate (default `1.0`) |

Copy `.env.example` if you start fresh.

## Scripts

| Script | Description |
|--------|-------------|
| `scripts/setup_local.sh` | Full local setup |
| `scripts/run_web.sh` | Start API + UI on port 8765 |
| `scripts/vendor_frontend.sh` | Download Three.js + TalkingHead |
| `scripts/benchmark_latency.sh` | Compare batch vs streaming latency |
| `scripts/test_groq.py` | Test Groq API key |

## Architecture

- **UI** — `web/static/` (avatar, SSE streaming chat)
- **API** — FastAPI (`src/yukti/api/`)
- **LLM** — LangChain + Groq
- **Memory** — SQLite (per-session messages) + Mem0 (per-user long-term)
- **TTS** — bizfyvoice API (sherpa-onnx Piper, remote)
- **Auth** — Google OAuth + JWT cookie

## Google login (when ready)

1. Set `AUTH_DISABLED=0` in `.env`
2. Add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
3. In Google Cloud Console, add redirect URI:  
   `http://127.0.0.1:8765/auth/google/callback`
4. Restart the server and open `/login`
