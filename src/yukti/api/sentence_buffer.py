"""Accumulate streamed LLM tokens and emit complete sentences."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s+|$)")


class SentenceBuffer:
    def __init__(self, *, min_chars: int = 4) -> None:
        self._buf = ""
        self._min_chars = min_chars

    def feed(self, text: str) -> list[str]:
        if not text:
            return []
        self._buf += text
        return self._drain(complete_only=True)

    def flush(self) -> str | None:
        remaining = self._drain(complete_only=False)
        out = remaining[0] if remaining else None
        return out

    def _drain(self, *, complete_only: bool) -> list[str]:
        sentences: list[str] = []
        while self._buf:
            if complete_only:
                m = _SENTENCE_END.search(self._buf)
                if not m:
                    break
                end = m.end()
            else:
                end = len(self._buf)

            chunk = self._buf[:end].strip()
            self._buf = self._buf[end:].lstrip()
            if len(chunk) >= self._min_chars:
                sentences.append(chunk)
            elif not complete_only and chunk:
                sentences.append(chunk)
        return sentences
