"""Paths and environment for the Yukti voice assistant."""

import os
from pathlib import Path

# Project root (yukti/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
STATIC_DIR = WEB_ROOT / "static"
ENV_FILE = PROJECT_ROOT / ".env"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "yukti.db")))

# Bundled Supertonic assets (no external supertonic/ repo)
ASSETS_ROOT = PROJECT_ROOT / "assets"
TTS_ONNX_DIR = ASSETS_ROOT / "onnx"
TTS_VOICES_DIR = ASSETS_ROOT / "voice_styles"

# Auth
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8765").rstrip("/")
AUTH_DISABLED = os.getenv("AUTH_DISABLED", "0") == "1"
JWT_COOKIE_NAME = "yukti_token"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))

# Mem0 local storage
MEM0_DIR = Path(os.getenv("MEM0_DIR", str(DATA_DIR / "mem0")))

# Chat history window sent to the LLM per request
CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "20"))
