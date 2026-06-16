"""Remote TTS via the bizfyvoice API (sherpa-onnx Piper)."""

from __future__ import annotations

import base64

import httpx

from yukti.config import BIZFY_VOICE_API_KEY, BIZFY_VOICE_SPEED, BIZFY_VOICE_URL

# Piper en_US-amy-low outputs 16 kHz mono WAV.
SAMPLE_RATE = 16000

_sync_client: httpx.Client | None = None
_async_client: httpx.AsyncClient | None = None


def _sync_http() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            base_url=BIZFY_VOICE_URL.rstrip("/"),
            headers={"X-Api-Key": BIZFY_VOICE_API_KEY},
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _sync_client


def _async_http() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            base_url=BIZFY_VOICE_URL.rstrip("/"),
            headers={"X-Api-Key": BIZFY_VOICE_API_KEY},
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _async_client


def check_health() -> None:
    r = _sync_http().get("/health")
    r.raise_for_status()


class BizfyVoiceTTS:
    """HTTP client matching the synthesize interface used by chat_pipeline."""

    sample_rate = SAMPLE_RATE

    def __init__(
        self,
        voice: str = "amy",
        lang: str = "en",
        speed: float | None = None,
    ):
        # Piper bundle is English-only; lang is kept for API compatibility.
        self.voice = map_voice(voice)
        self.lang = lang
        self.speed = speed if speed is not None else BIZFY_VOICE_SPEED

    async def synthesize_wav_b64(self, text: str) -> str:
        payload = {"text": text.strip(), "voice": self.voice, "speed": self.speed}
        r = await _async_http().post("/tts", json=payload)
        r.raise_for_status()
        if not r.content:
            raise RuntimeError("bizfyvoice returned empty audio")
        return base64.b64encode(r.content).decode("ascii")

    def synthesize_wav_b64_sync(self, text: str) -> str:
        payload = {"text": text.strip(), "voice": self.voice, "speed": self.speed}
        r = _sync_http().post("/tts", json=payload)
        r.raise_for_status()
        if not r.content:
            raise RuntimeError("bizfyvoice returned empty audio")
        return base64.b64encode(r.content).decode("ascii")


def map_voice(voice: str) -> str:
    """Map legacy Supertonic style IDs (F1, M2, …) to Piper's single voice."""
    if not voice or voice.startswith(("F", "M")):
        return "amy"
    return voice


def warmup() -> None:
    check_health()
    BizfyVoiceTTS().synthesize_wav_b64_sync("Hi.")
