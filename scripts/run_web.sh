#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/uvicorn" ]]; then
  echo "Run: bash scripts/setup_local.sh" >&2
  exit 1
fi
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source <(grep -v '^\s*#' "$ROOT/.env" | grep -v '^\s*$' | sed 's/^/export /')
  set +a
fi
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8765}"
echo "Listening on http://${HOST}:${PORT}  (LAN: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT})"
exec .venv/bin/uvicorn yukti.api.app:app --host "$HOST" --port "$PORT" --reload
