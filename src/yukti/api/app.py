"""FastAPI web server for Yukti."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from yukti.api.auth_routes import router as auth_router
from yukti.api.chat_pipeline import run_batch_turn, stream_chat_events
from yukti.api.preload import (
    avatar_response,
    get_preload_status,
    run_startup_preload,
    vendor_response,
)
from yukti.api.schemas import ChatRequest, ChatResponse, SessionListResponse
from yukti.auth.deps import get_optional_user, require_user
from yukti.config import AUTH_DISABLED, ENV_FILE, SECRET_KEY, STATIC_DIR, WEB_ROOT
from yukti.db.repository import ChatRepository, User
from yukti.db.schema import init_db
from yukti.llm import groq as groq_llm
from yukti.services.conversation import get_conversation_service
from yukti.tts import BizfyVoiceTTS
from yukti.tts.bizfyvoice import map_voice

MAX_TRANSCRIBE_BYTES = 12 * 1024 * 1024

load_dotenv(ENV_FILE)

_tts: BizfyVoiceTTS | None = None
_repo = ChatRepository()
_conv = get_conversation_service()


def get_tts(voice: str, lang: str) -> BizfyVoiceTTS:
    """Return a shared bizfyvoice TTS client (lightweight HTTP, no local models)."""
    global _tts
    mapped = map_voice(voice)
    if _tts is None:
        _tts = BizfyVoiceTTS(voice=mapped, lang=lang)
    else:
        _tts.voice = mapped
        _tts.lang = lang
    return _tts


def _mem0_warmup() -> None:
    from yukti.auth import deps as auth_deps

    user = auth_deps._dev_user_record()
    _conv.memory_context(user, "warmup")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    run_startup_preload(get_tts, mem0_warmup=_mem0_warmup if _conv._mem0.enabled else None)
    mem0 = _conv._mem0
    if mem0.enabled:
        print("Mem0 long-term memory: enabled")
    else:
        print(f"Mem0 long-term memory: disabled ({mem0._init_error or 'unknown'})")
    if AUTH_DISABLED:
        print("AUTH_DISABLED=1 — using dev user without login")
    print("Ready.")
    yield


app = FastAPI(title="Yukti Voice Assistant", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)


@app.get("/login")
async def login_page():
    return FileResponse(WEB_ROOT / "login.html")


@app.get("/manifest.webmanifest")
async def pwa_manifest():
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/offline.html")
async def offline_page():
    return FileResponse(WEB_ROOT / "offline.html")


@app.get("/")
async def index(user: User | None = Depends(get_optional_user)):
    if user is None and not AUTH_DISABLED:
        return RedirectResponse(url="/login")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/ready")
async def api_ready():
    """Preload status — models warmed at startup."""
    return JSONResponse(get_preload_status())


@app.get("/static/avatars/{filename}")
async def static_avatar_cached(filename: str):
    """Preloaded GLB avatars (RAM); falls through to disk via 404 if missing."""
    resp = avatar_response(filename)
    if resp is None:
        path = STATIC_DIR / "avatars" / filename
        if path.is_file():
            return FileResponse(path, media_type="model/gltf-binary")
        raise HTTPException(status_code=404, detail="Avatar not found")
    return resp


@app.get("/static/vendor/{vendor_path:path}")
async def static_vendor_cached(vendor_path: str):
    """Preloaded Three.js / TalkingHead modules when configured."""
    rel = f"vendor/{vendor_path}"
    resp = vendor_response(rel)
    if resp is None:
        path = STATIC_DIR / rel
        if path.is_file():
            return FileResponse(path)
        raise HTTPException(status_code=404)
    return resp


@app.get("/api/avatars")
async def list_avatars(user: User = Depends(require_user)):
    avatars_dir = STATIC_DIR / "avatars"
    files = []
    if avatars_dir.is_dir():
        for path in sorted(avatars_dir.glob("*.glb")):
            files.append({"name": path.stem, "bytes": path.stat().st_size})
    return {"ok": bool(files), "files": files}


@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(user: User = Depends(require_user)):
    sessions = _repo.list_sessions(user.id)
    return SessionListResponse(
        sessions=[
            {"id": s.id, "title": s.title or "Chat", "updated_at": s.updated_at}
            for s in sessions
        ]
    )


@app.post("/api/sessions")
async def create_session(user: User = Depends(require_user)):
    sid = _conv.ensure_session(None, user)
    return {"session_id": sid}


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(body: ChatRequest, user: User = Depends(require_user)):
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    session_id = _conv.ensure_session(body.session_id, user)

    try:
        reply, _new_history, audio_b64, _metrics = await run_batch_turn(
            message,
            user,
            session_id,
            _conv,
            get_tts=get_tts,
            voice=body.voice,
            lang=body.lang,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(reply=reply, audio_base64=audio_b64, session_id=session_id)


@app.post("/api/chat/stream", response_class=EventSourceResponse)
async def api_chat_stream(body: ChatRequest, user: User = Depends(require_user)):
    """Stream LLM tokens and per-sentence TTS audio via Server-Sent Events."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    try:
        session_id = _conv.ensure_session(body.session_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    async for event in stream_chat_events(
        message,
        user,
        session_id,
        _conv,
        get_tts=get_tts,
        voice=body.voice,
        lang=body.lang,
    ):
        if event.get("type") == "error":
            yield event
            return
        if event.get("type") == "done":
            event.pop("new_history", None)
        yield event


@app.post("/api/transcribe")
async def api_transcribe(
    audio: UploadFile = File(...),
    lang: str = Form("en"),
    user: User = Depends(require_user),
):
    """Speech-to-text for mobile browsers (HTTPS + MediaRecorder)."""
    _ = user
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(raw) > MAX_TRANSCRIBE_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 12 MB)")

    lang_code = (lang or "en").split("-")[0].lower()
    whisper_lang = None if lang_code in ("", "auto") else lang_code
    filename = audio.filename or "audio.webm"

    try:
        text = await groq_llm.transcribe_audio(
            raw,
            filename=filename,
            language=whisper_lang,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {exc}") from exc

    if not text:
        raise HTTPException(status_code=422, detail="No speech detected")
    return {"text": text}


@app.post("/api/reset")
async def api_reset(session_id: str, user: User = Depends(require_user)):
    try:
        _conv.clear_session(session_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True}


# Remaining /static/* (avatars + key vendor paths use dedicated cached routes above)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
