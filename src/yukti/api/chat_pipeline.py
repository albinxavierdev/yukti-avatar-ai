"""Batch and streaming chat pipelines with timing metrics."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from yukti.api.sentence_buffer import SentenceBuffer
from yukti.config import TTS_MAX_CHUNK_CHARS, TTS_MIN_CHUNK_CHARS
from yukti.db.repository import User
from yukti.services.conversation import ConversationService


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
    audio_b64 = await tts.synthesize_wav_b64(reply)
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
    """SSE: LLM tokens stream immediately; TTS runs in parallel (ordered chunks)."""
    t0 = time.perf_counter()
    reply_parts: list[str] = []
    first_text_at: float | None = None
    first_audio_at: float | None = None
    llm_done_at: float | None = None
    tts_total_ms = 0.0
    audio_index = 0

    yield {"type": "session", "session_id": session_id}

    try:
        tts = get_tts(voice, lang)
        buf = SentenceBuffer(
            min_chars=TTS_MIN_CHUNK_CHARS,
            max_chars=TTS_MAX_CHUNK_CHARS,
        )

        # Queues bridge LLM producer ↔ TTS worker ↔ SSE consumer
        speak_q: asyncio.Queue[str | None] = asyncio.Queue()
        audio_q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        llm_finished = asyncio.Event()

        async def tts_worker() -> None:
            nonlocal audio_index, first_audio_at, tts_total_ms
            while True:
                chunk = await speak_q.get()
                if chunk is None:
                    break
                t_tts0 = time.perf_counter()
                audio_b64 = await tts.synthesize_wav_b64(chunk)
                t_tts1 = time.perf_counter()
                tts_total_ms += (t_tts1 - t_tts0) * 1000
                if first_audio_at is None:
                    first_audio_at = t_tts1
                await audio_q.put(
                    {
                        "type": "audio",
                        "index": audio_index,
                        "text": chunk,
                        "audio_base64": audio_b64,
                    }
                )
                audio_index += 1
            await audio_q.put(None)

        tts_task = asyncio.create_task(tts_worker())

        async def llm_producer() -> None:
            nonlocal first_text_at, llm_done_at
            async for delta in conv.stream(
                user=user,
                session_id=session_id,
                message=message,
            ):
                if first_text_at is None and delta.strip():
                    first_text_at = time.perf_counter()
                reply_parts.append(delta)
                await audio_q.put({"type": "text_delta", "delta": delta})
                for chunk in buf.feed(delta):
                    await speak_q.put(chunk)

            llm_done_at = time.perf_counter()
            remainder = buf.flush()
            if remainder:
                await speak_q.put(remainder)
            await speak_q.put(None)
            llm_finished.set()

        llm_task = asyncio.create_task(llm_producer())

        # Multiplex: yield text/audio as they arrive; TTS no longer blocks LLM tokens
        tts_done = False
        while True:
            if llm_finished.is_set() and tts_done and audio_q.empty():
                break

            try:
                event = await asyncio.wait_for(audio_q.get(), timeout=0.05)
            except asyncio.TimeoutError:
                if llm_task.done() and llm_task.exception():
                    raise llm_task.exception()  # type: ignore[misc]
                continue

            if event is None:
                tts_done = True
                continue

            if event.get("type") == "text_delta":
                yield event
            elif event.get("type") == "audio":
                yield event

        await llm_task
        await tts_task

        reply = "".join(reply_parts).strip()
        new_history = await asyncio.to_thread(
            conv.persist_turn, session_id, user, message, reply
        )
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
