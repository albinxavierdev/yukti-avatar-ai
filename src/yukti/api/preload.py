"""Startup preloading: TTS warm-up, avatar GLBs, frontend vendor assets."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from starlette.responses import Response

from yukti.config import (
    BIZFY_VOICE_URL,
    PRELOAD_AVATARS,
    PRELOAD_TTS_WARMUP,
    PRELOAD_VENDOR_ASSETS,
    STATIC_DIR,
)
from yukti.tts import BizfyVoiceTTS
from yukti.tts.bizfyvoice import warmup as warmup_bizfyvoice

# In-memory caches (populated at startup)
_avatar_bytes: dict[str, bytes] = {}
_vendor_bytes: dict[str, bytes] = {}
_status: dict[str, Any] = {"ready": False}


def avatar_response(filename: str) -> Response | None:
    """Serve a preloaded avatar GLB from RAM."""
    data = _avatar_bytes.get(filename)
    if data is None:
        return None
    return Response(
        content=data,
        media_type="model/gltf-binary",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(len(data)),
        },
    )


def get_preload_status() -> dict[str, Any]:
    return dict(_status)


def _warm_file(path: Path, dest: dict[str, bytes], key: str) -> int:
    data = path.read_bytes()
    dest[key] = data
    return len(data)


def preload_avatar_glbs() -> list[str]:
    avatars_dir = STATIC_DIR / "avatars"
    loaded: list[str] = []
    if not avatars_dir.is_dir():
        return loaded
    for path in sorted(avatars_dir.glob("*.glb")):
        nbytes = _warm_file(path, _avatar_bytes, path.name)
        loaded.append(f"{path.stem} ({nbytes // 1024} KB)")
    return loaded


def preload_vendor_assets() -> list[str]:
    """Warm TalkingHead / Three / lip-sync into RAM for fast static serving."""
    paths = [
        STATIC_DIR / "vendor" / "three@0.170.0" / "build" / "three.module.js",
        STATIC_DIR
        / "vendor"
        / "talkinghead"
        / "modules"
        / "talkinghead.mjs",
        STATIC_DIR / "vendor" / "talkinghead" / "modules" / "lipsync-en.mjs",
    ]
    loaded: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        rel = path.relative_to(STATIC_DIR).as_posix()
        nbytes = _warm_file(path, _vendor_bytes, rel)
        loaded.append(f"{rel} ({nbytes // 1024} KB)")
    return loaded


def vendor_response(relative_path: str) -> Response | None:
    data = _vendor_bytes.get(relative_path)
    if data is None:
        return None
    media = "application/javascript"
    if relative_path.endswith(".mjs"):
        media = "text/javascript"
    return Response(
        content=data,
        media_type=media,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(len(data)),
        },
    )


def run_startup_preload(
    get_tts: Callable[[str, str], BizfyVoiceTTS],
    *,
    mem0_warmup: Callable[[], None] | None = None,
) -> None:
    """Blocking preload run from FastAPI lifespan (before accepting traffic)."""
    global _status
    t0 = time.perf_counter()
    steps: dict[str, Any] = {"tts_backend": BIZFY_VOICE_URL}

    print(f"Warming bizfyvoice TTS at {BIZFY_VOICE_URL} …")
    t1 = time.perf_counter()
    if PRELOAD_TTS_WARMUP:
        warmup_bizfyvoice()
        steps["tts_warmup_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    else:
        get_tts("amy", "en")
        steps["tts_warmup_ms"] = 0

    if PRELOAD_AVATARS:
        t3 = time.perf_counter()
        steps["avatars"] = preload_avatar_glbs()
        steps["avatars_ms"] = round((time.perf_counter() - t3) * 1000, 1)

    if PRELOAD_VENDOR_ASSETS:
        t4 = time.perf_counter()
        steps["vendor"] = preload_vendor_assets()
        steps["vendor_ms"] = round((time.perf_counter() - t4) * 1000, 1)

    if mem0_warmup:
        t5 = time.perf_counter()
        try:
            mem0_warmup()
            steps["mem0"] = "warmed"
        except Exception as exc:
            steps["mem0"] = f"skipped ({exc})"
        steps["mem0_ms"] = round((time.perf_counter() - t5) * 1000, 1)

    steps["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    _status = {"ready": True, **steps}
    print(f"Preload complete in {steps['total_ms']} ms")
