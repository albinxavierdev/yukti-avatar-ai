"""Session chat history (SQLite) + Mem0 long-term memory."""

from __future__ import annotations

from functools import lru_cache

from yukti.db.repository import ChatRepository, User
from yukti.llm import langchain_groq
from yukti.memory.mem0_store import get_mem0_store


class ConversationService:
    def __init__(self) -> None:
        self._db = ChatRepository()
        self._mem0 = get_mem0_store()

    def ensure_session(self, session_id: str | None, user: User) -> str:
        return self._db.ensure_session(session_id, user.id)

    def load_history(self, session_id: str) -> list[dict]:
        return self._db.get_messages(session_id)

    def memory_context(self, user: User, query: str) -> str:
        return self._mem0.search_context(user.id, query)

    def chat(
        self,
        *,
        user: User,
        session_id: str,
        message: str,
        history: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        hist = history if history is not None else self.load_history(session_id)
        mem_ctx = self.memory_context(user, message)
        reply, new_history = langchain_groq.chat(
            message, hist, memory_context=mem_ctx
        )
        self._db.append_turn(session_id, message, reply)
        self._mem0.add_turn(user.id, message, reply)
        return reply, new_history

    async def stream(
        self,
        *,
        user: User,
        session_id: str,
        message: str,
        history: list[dict] | None = None,
    ):
        hist = history if history is not None else self.load_history(session_id)
        mem_ctx = self.memory_context(user, message)
        async for delta in langchain_groq.chat_stream(
            message, hist, memory_context=mem_ctx
        ):
            yield delta

    def persist_turn(
        self, session_id: str, user: User, user_message: str, assistant_message: str
    ) -> list[dict]:
        new_history = self._db.append_turn(session_id, user_message, assistant_message)
        self._mem0.add_turn(user.id, user_message, assistant_message)
        return new_history

    def clear_session(self, session_id: str, user: User) -> None:
        self._db.clear_session(session_id, user.id)


@lru_cache(maxsize=1)
def get_conversation_service() -> ConversationService:
    return ConversationService()
