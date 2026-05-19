"""Mem0 long-term memory per user (local vector store)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from yukti.config import GROQ_API_KEY, GROQ_MODEL, MEM0_DIR


class Mem0Store:
    def __init__(self) -> None:
        self._memory = None
        self._enabled = False
        self._init_error: str | None = None
        self._try_init()

    def _try_init(self) -> None:
        try:
            from mem0 import Memory

            MEM0_DIR.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MEM0_DIR", str(MEM0_DIR))

            config: dict[str, Any] = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "yukti_memories",
                        "path": str(MEM0_DIR / "chroma"),
                    },
                },
                "embedder": {
                    "provider": "fastembed",
                    "config": {
                        "model": "BAAI/bge-small-en-v1.5",
                    },
                },
                "history_db_path": str(MEM0_DIR / "history.db"),
            }
            if GROQ_API_KEY:
                config["llm"] = {
                    "provider": "groq",
                    "config": {
                        "model": GROQ_MODEL,
                        "api_key": GROQ_API_KEY,
                    },
                }

            self._memory = Memory.from_config(config)
            self._enabled = True
        except Exception as exc:
            try:
                from mem0 import Memory

                self._memory = Memory()
                self._enabled = True
            except Exception as exc2:
                self._init_error = f"{exc}; fallback: {exc2}"
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._memory is not None

    def search_context(self, user_id: int, query: str, *, limit: int = 5) -> str:
        if not self.enabled or not query.strip():
            return ""
        try:
            results = self._memory.search(query=query, user_id=str(user_id), limit=limit)
            memories = results.get("results") if isinstance(results, dict) else results
            if not memories:
                return ""
            lines: list[str] = []
            for item in memories:
                text = item.get("memory") if isinstance(item, dict) else str(item)
                if text:
                    lines.append(f"- {text}")
            if not lines:
                return ""
            return "Relevant memories about this user:\n" + "\n".join(lines)
        except Exception:
            return ""

    def add_turn(self, user_id: int, user_message: str, assistant_message: str) -> None:
        if not self.enabled:
            return
        try:
            self._memory.add(
                [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_message},
                ],
                user_id=str(user_id),
                metadata={"source": "yukti"},
            )
        except Exception:
            pass


@lru_cache(maxsize=1)
def get_mem0_store() -> Mem0Store:
    return Mem0Store()
