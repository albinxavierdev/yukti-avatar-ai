"""Batch and streaming chat pipelines with timing metrics."""

from __future__ import annotations

import asyncio
import base64
import io
import time
from collections.abc import AsyncIterator
from typing import Any

import soundfile as sf

from yukti.api.pools import tts_pool
from yukti.api.sentence_buffer import SentenceBuffer
from yukti.db.repository import User
from yukti.services.conversation import ConversationService
from yukti.tts import LocalTTS


def synthesize_wav_b64(tts: LocalTTS, text: str) -> str:
    audio = tts.synthesize(text)
    buf = io.BytesIO()
    sf.write(buf, audio, tts.sample_rate, format="WAV")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def run_batch_turn(
    message: str,
    user: User,
    session_id: str,
    conv: ConversationService,
    *,
    get_tts,
    voice: str,
    lang: str,
) -> tuple[str, list[dict], str, dict[str, float]]:
    """Blocking LLM + TTS offloaded to thread pools; returns timings in ms."""
    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()

    reply, new_history = await loop.run_in_executor(
        None,
        lambda: conv.chat(
            user=user, session_id=session_id, message=message
        ),
    )
    t_llm = time.perf_counter()

    tts = get_tts(voice, lang)
    audio_b64 = await loop.run_in_executor(
        tts_pool, lambda: synthesize_wav_b64(tts, reply)
    )
    t_done = time.perf_counter()

    metrics = {
        "llm_ms": round((t_llm - t0) * 1000, 1),
        "tts_ms": round((t_done - t_llm) * 1000, 1),
        "total_ms": round((t_done - t0) * 1000, 1),
        "ttf_audio_ms": round((t_done - t0) * 1000, 1),
    }
    return reply, new_history, audio_b64, metrics


async def stream_chat_events(
    message: str,
    user: User,
    session_id: str,
    conv: ConversationService,
    *,
    get_tts,
    voice: str,
    lang: str,
) -> AsyncIterator[dict[str, Any]]:
    """SSE payload dicts: session, text, audio, done, error."""
    t0 = time.perf_counter()
    reply_parts: list[str] = []
    audio_index = 0
    first_text_at: float | None = None
    first_audio_at: float | None = None
    llm_done_at: float | None = None
    tts_total_ms = 0.0
    history = conv.load_history(session_id)

    yield {"type": "session", "session_id": session_id}

    try:
        tts = get_tts(voice, lang)
        buf = SentenceBuffer()
        loop = asyncio.get_running_loop()

        async for delta in conv.stream(
            user=user, session_id=session_id, message=message, history=history
        ):
            if first_text_at is None and delta.strip():
                first_text_at = time.perf_counter()
            reply_parts.append(delta)
            yield {"type": "text_delta", "delta": delta}

            for sentence in buf.feed(delta):
                t_tts0 = time.perf_counter()
                audio_b64 = await loop.run_in_executor(
                    tts_pool, lambda s=sentence: synthesize_wav_b64(tts, s)
                )
                t_tts1 = time.perf_counter()
                tts_total_ms += (t_tts1 - t_tts0) * 1000
                if first_audio_at is None:
                    first_audio_at = t_tts1
                payload = {
                    "type": "audio",
                    "index": audio_index,
                    "text": sentence,
                    "audio_base64": audio_b64,
                }
                audio_index += 1
                yield payload

        llm_done_at = time.perf_counter()
        reply = "".join(reply_parts).strip()
        remainder = buf.flush()
        if remainder:
            t_tts0 = time.perf_counter()
            audio_b64 = await loop.run_in_executor(
                tts_pool, lambda: synthesize_wav_b64(tts, remainder)
            )
            t_tts1 = time.perf_counter()
            tts_total_ms += (t_tts1 - t_tts0) * 1000
            if first_audio_at is None:
                first_audio_at = t_tts1
            yield {
                "type": "audio",
                "index": audio_index,
                "text": remainder,
                "audio_base64": audio_b64,
            }
            audio_index += 1

        new_history = conv.persist_turn(session_id, user, message, reply)
        t_done = time.perf_counter()
        metrics = {
            "ttf_text_ms": round((first_text_at - t0) * 1000, 1) if first_text_at else None,
            "ttf_audio_ms": round((first_audio_at - t0) * 1000, 1) if first_audio_at else None,
            "llm_ms": round((llm_done_at - t0) * 1000, 1) if llm_done_at else None,
            "tts_ms": round(tts_total_ms, 1),
            "total_ms": round((t_done - t0) * 1000, 1),
            "audio_chunks": audio_index,
        }
        yield {
            "type": "done",
            "reply": reply,
            "session_id": session_id,
            "metrics": metrics,
            "new_history": new_history,
        }
    except Exception as exc:
        yield {"type": "error", "detail": str(exc)}
