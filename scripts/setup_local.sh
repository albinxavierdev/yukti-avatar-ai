#!/usr/bin/env bash
# One-shot local dev setup for Yukti.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Yukti local setup"
echo "    Project: $ROOT"
echo ""

# --- Python venv ---
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "==> Creating virtualenv…"
  python3 -m venv "$ROOT/.venv"
fi
echo "==> Installing Python dependencies…"
"$ROOT/.venv/bin/pip" install -q --upgrade pip
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt"

# --- .env ---
ENV_FILE="$ROOT/.env"
EXAMPLE="$ROOT/.env.example"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating .env from .env.example…"
  cp "$EXAMPLE" "$ENV_FILE"
fi

ensure_env() {
  local key="$1"
  local default="$2"
  if ! grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    echo "${key}=${default}" >> "$ENV_FILE"
    echo "    + ${key}"
  fi
}

# Local dev defaults (does not overwrite existing keys)
ensure_env "AUTH_DISABLED" "0"
ensure_env "BASE_URL" "http://127.0.0.1:8765"
ensure_env "DATABASE_PATH" "data/yukti.db"
ensure_env "MEM0_DIR" "data/mem0"
ensure_env "CHAT_HISTORY_LIMIT" "20"

if ! grep -q "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null || grep -q "^SECRET_KEY=generate" "$ENV_FILE" 2>/dev/null; then
  SECRET="$("$ROOT/.venv/bin/python" -c "import secrets; print(secrets.token_urlsafe(32))")"
  if grep -q "^SECRET_KEY=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" "$ENV_FILE"
  else
    echo "SECRET_KEY=${SECRET}" >> "$ENV_FILE"
  fi
  echo "    + SECRET_KEY (generated)"
fi

if grep -q "^GROQ_API_KEY=your_groq" "$ENV_FILE" 2>/dev/null || ! grep -q "^GROQ_API_KEY=." "$ENV_FILE" 2>/dev/null; then
  echo ""
  echo "!! Add GROQ_API_KEY to .env (get one at https://console.groq.com)"
fi

# --- PWA icons ---
echo "==> Generating PWA icons…"
"$ROOT/.venv/bin/pip" install -q Pillow 2>/dev/null || true
"$ROOT/.venv/bin/python" "$ROOT/scripts/generate_pwa_icons.py" || echo "    (skipped — install Pillow to generate icons)"

# --- Frontend vendor (Three.js + TalkingHead) ---
if [[ ! -d "$ROOT/web/static/vendor/talkinghead/modules" ]]; then
  echo "==> Downloading frontend vendor assets…"
  bash "$ROOT/scripts/vendor_frontend.sh"
else
  echo "==> Frontend vendor: OK"
fi

# --- TTS ONNX assets ---
if [[ ! -f "$ROOT/assets/onnx/tts.json" ]]; then
  echo "==> Downloading Supertonic TTS assets (may take a few minutes)…"
  bash "$ROOT/scripts/setup_assets.sh"
else
  echo "==> TTS assets: OK"
fi

# --- SQLite DB init ---
echo "==> Initializing database…"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
"$ROOT/.venv/bin/python" -c "
from dotenv import load_dotenv
from yukti.config import ENV_FILE
load_dotenv(ENV_FILE)
from yukti.db.schema import init_db
init_db()
print('    Database ready')
"

echo "==> Seeding dummy user (test / test123)…"
"$ROOT/.venv/bin/python" "$ROOT/scripts/seed_dummy_user.py"

# --- Optional: warm Mem0 (first run downloads embedding model) ---
echo "==> Checking Mem0 (first run may download a small embedding model)…"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
set -a
# shellcheck source=/dev/null
source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | sed 's/^/export /')
set +a
"$ROOT/.venv/bin/python" -c "
from dotenv import load_dotenv
from yukti.config import ENV_FILE
load_dotenv(ENV_FILE, override=True)
from yukti.memory.mem0_store import get_mem0_store
get_mem0_store.cache_clear()
m = get_mem0_store()
print('    Mem0:', 'enabled' if m.enabled else f'disabled ({m._init_error or \"unknown\"})')
" || true

echo ""
echo "==> Setup complete"
echo ""
echo "Start the app:"
echo "  cd $ROOT && bash scripts/run_web.sh"
echo ""
echo "Then open: http://127.0.0.1:8765"
echo ""
if grep -q "^AUTH_DISABLED=1" "$ENV_FILE" 2>/dev/null; then
  echo "AUTH_DISABLED=1 — no Google login required for local dev."
else
  echo "Sign in at: http://127.0.0.1:8765/login"
  echo "Google redirect URI: http://127.0.0.1:8765/auth/google/callback"
fi
echo ""
