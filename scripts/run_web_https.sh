#!/usr/bin/env bash
# Run Yukti with a self-signed HTTPS cert (needed for mic on phones over LAN).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CERT_DIR="${ROOT}/data/certs"
KEY="${CERT_DIR}/key.pem"
CERT="${CERT_DIR}/cert.pem"

if [[ ! -f "$KEY" || ! -f "$CERT" ]]; then
  echo "==> Generating self-signed certificate (data/certs/)…"
  mkdir -p "$CERT_DIR"
  IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  SAN="DNS:localhost,DNS:$(hostname -f 2>/dev/null || echo localhost)"
  if [[ -n "$IP" ]]; then
    SAN="${SAN},IP:127.0.0.1,IP:${IP}"
  fi
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY" -out "$CERT" -days 825 \
    -subj "/CN=Yukti Local" \
    -addext "subjectAltName=${SAN}" 2>/dev/null || \
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY" -out "$CERT" -days 825 \
    -subj "/CN=Yukti Local"
fi

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8765}"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo ""
echo "HTTPS (required for microphone on phones):"
echo "  https://127.0.0.1:${PORT}"
if [[ -n "$IP" ]]; then
  echo "  https://${IP}:${PORT}"
fi
echo ""
echo "On your phone: open the https://… URL, accept the certificate warning, then allow microphone."
echo "Set BASE_URL in .env to the https URL you use (e.g. https://${IP:-127.0.0.1}:${PORT})."
echo ""

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source <(grep -v '^\s*#' "$ROOT/.env" | grep -v '^\s*$' | sed 's/^/export /')
  set +a
fi
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/uvicorn" yukti.api.app:app \
  --host "$HOST" --port "$PORT" --reload \
  --ssl-keyfile "$KEY" --ssl-certfile "$CERT"
