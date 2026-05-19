#!/usr/bin/env bash
# One-time download: Three.js + TalkingHead into web/static/vendor (offline UI).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/web/static/vendor"
THREE_VER="0.170.0"
TH_TAG="v1.4.0"

rm -rf "$VENDOR"
mkdir -p "$VENDOR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "==> Three.js ${THREE_VER}"
curl -fsSL "https://registry.npmjs.org/three/-/three-${THREE_VER}.tgz" -o "$tmpdir/three.tgz"
tar -xzf "$tmpdir/three.tgz" -C "$tmpdir"
mkdir -p "$VENDOR/three@${THREE_VER}/examples"
mv "$tmpdir/package/build" "$VENDOR/three@${THREE_VER}/build"
mv "$tmpdir/package/examples/jsm" "$VENDOR/three@${THREE_VER}/examples/jsm"

echo "==> TalkingHead ${TH_TAG}"
curl -fsSL "https://github.com/met4citizen/TalkingHead/archive/refs/tags/${TH_TAG}.tar.gz" -o "$tmpdir/th.tar.gz"
tar -xzf "$tmpdir/th.tar.gz" -C "$tmpdir"
th_dir="$(find "$tmpdir" -maxdepth 1 -type d -name 'TalkingHead-*' | head -1)"
mkdir -p "$VENDOR/talkinghead"
mv "$th_dir/modules" "$VENDOR/talkinghead/modules"

echo "Done. Vendor tree:"
du -sh "$VENDOR"/* 2>/dev/null || true
ls -la "$VENDOR/talkinghead/modules" | head -20
