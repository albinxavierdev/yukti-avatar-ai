#!/usr/bin/env bash
# Re-download Supertonic ONNX + voices if assets/ is missing (e.g. fresh clone without LFS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$ROOT/assets"
ONNX="$ASSETS/onnx"
VOICES="$ASSETS/voice_styles"

if [[ -f "$ONNX/tts.json" && -f "$VOICES/F2.json" ]]; then
  echo "Assets already present at $ASSETS"
  exit 0
fi

echo "Downloading Supertonic assets (Supertone/supertonic-3)…"
mkdir -p "$ASSETS"
if ! command -v huggingface-cli &>/dev/null; then
  pip install -q "huggingface_hub[cli]"
fi
huggingface-cli download Supertone/supertonic-3 --local-dir "$ASSETS/hf" --local-dir-use-symlinks False
mkdir -p "$ONNX" "$VOICES"
cp -r "$ASSETS/hf/onnx/"* "$ONNX/" 2>/dev/null || cp -r "$ASSETS/hf/"* "$ONNX/" 2>/dev/null || true
cp -r "$ASSETS/hf/voice_styles/"* "$VOICES/" 2>/dev/null || true
rm -rf "$ASSETS/hf"
echo "Done. Verify: ls $ONNX"
