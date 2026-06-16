"""Accumulate streamed LLM tokens and emit TTS-sized chunks as early as possible."""

from __future__ import annotations

import re

# Sentence or clause boundary — start TTS without waiting for a full stop.
_CHUNK_END = re.compile(r"(?<=[.!?,:;])(?:\s+|$)")


class SentenceBuffer:
    """Buffers LLM tokens; yields chunks on punctuation or max length (word-safe).

    Short fragments (e.g. "Hello!") are held and prepended to the next chunk instead
    of being discarded before TTS.
    """

    def __init__(
        self,
        *,
        min_chars: int = 3,
        max_chars: int = 72,
    ) -> None:
        self._buf = ""
        self._pending = ""
        self._min_chars = min_chars
        self._max_chars = max_chars

    def feed(self, text: str) -> list[str]:
        if not text:
            return []
        self._buf += text
        return self._drain(complete_only=True)

    def flush(self) -> str | None:
        if self._pending:
            self._buf = (
                f"{self._pending} {self._buf}".strip() if self._buf else self._pending
            )
            self._pending = ""
        chunks = self._drain(complete_only=False)
        if chunks:
            return chunks[0] if len(chunks) == 1 else " ".join(chunks)
        return None

    def _emit(self, chunk: str, out: list[str], *, allow_short: bool) -> None:
        if not chunk:
            return
        if self._pending:
            chunk = f"{self._pending} {chunk}".strip()
            self._pending = ""
        if len(chunk) >= self._min_chars or allow_short:
            out.append(chunk)
        else:
            self._pending = chunk

    def _drain(self, *, complete_only: bool) -> list[str]:
        chunks: list[str] = []
        while self._buf:
            end: int | None = None

            if complete_only:
                m = _CHUNK_END.search(self._buf)
                if m:
                    end = m.end()
                elif len(self._buf) >= self._max_chars:
                    end = self._word_safe_cut(self._max_chars)
            else:
                end = len(self._buf)

            if end is None:
                break

            piece = self._buf[:end].strip()
            self._buf = self._buf[end:].lstrip()
            self._emit(piece, chunks, allow_short=not complete_only)

        return chunks

    def _word_safe_cut(self, max_pos: int) -> int:
        """Prefer breaking at the last space before max_pos."""
        segment = self._buf[:max_pos]
        space = segment.rfind(" ")
        if space >= 1:
            return space + 1
        return max_pos
