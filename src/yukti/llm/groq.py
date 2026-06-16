"""Groq Cloud LLM client (OpenAI-compatible API)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

from yukti.config import ENV_FILE, GROQ_WHISPER_MODEL

load_dotenv(ENV_FILE)

DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_SYSTEM = """You are Yukti, a voice assistant built by Bizfy Solution.

Identity (always stay consistent):
- Your name is Yukti. You represent Bizfy Solution.
- You are helpful, professional, and warm. You are always ready to help.
- When tasks, tools, or integrations are assigned and configured properly, you can help users get work done through this assistant.

Honesty (never break these rules):
- If you do not know something, do not have access to data, or cannot do something, say so clearly and briefly. Do not guess or invent facts.
- Never hallucinate names, numbers, policies, APIs, or capabilities you were not given.
- Do not pretend to have performed actions you cannot perform.

Style:
- Reply in 1–2 short sentences unless the user asks for more detail.
- Be natural and conversational for voice.
- Stay on topic and keep the same identity in every turn."""


def _api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return api_key


def get_client() -> OpenAI:
    return OpenAI(api_key=_api_key(), base_url="https://api.groq.com/openai/v1")


def get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=_api_key(), base_url="https://api.groq.com/openai/v1")


def _build_messages(
    user_message: str,
    history: list[dict] | None,
    *,
    system: str,
) -> list[dict]:
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def chat(
    user_message: str,
    history: list[dict] | None = None,
    *,
    system: str = DEFAULT_SYSTEM,
    model: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> tuple[str, list[dict]]:
    """Send a message and return (assistant_reply, updated_history)."""
    client = get_client()
    model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    messages = _build_messages(user_message, history, system=system)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    reply = response.choices[0].message.content or ""
    new_history = (history or []) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    return reply, new_history


def chat_stream_sync(
    user_message: str,
    history: list[dict] | None = None,
    *,
    system: str = DEFAULT_SYSTEM,
    model: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> Iterator[str]:
    """Yield text deltas from Groq (blocking; use from a thread)."""
    client = get_client()
    model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    messages = _build_messages(user_message, history, system=system)
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def chat_stream(
    user_message: str,
    history: list[dict] | None = None,
    *,
    system: str = DEFAULT_SYSTEM,
    model: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """Yield text deltas from Groq without blocking the event loop."""
    client = get_async_client()
    model = model or os.getenv("GROQ_MODEL", DEFAULT_MODEL)
    messages = _build_messages(user_message, history, system=system)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def transcribe_audio(
    audio_bytes: bytes,
    *,
    filename: str = "audio.webm",
    language: str | None = None,
    model: str | None = None,
) -> str:
    """Transcribe speech audio via Groq Whisper (OpenAI-compatible API)."""
    import io

    client = get_async_client()
    model = model or GROQ_WHISPER_MODEL
    buf = io.BytesIO(audio_bytes)
    buf.name = filename
    kwargs: dict = {"model": model, "file": buf}
    if language:
        kwargs["language"] = language
    result = await client.audio.transcriptions.create(**kwargs)
    return (result.text or "").strip()
