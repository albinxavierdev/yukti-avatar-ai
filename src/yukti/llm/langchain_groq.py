"""LangChain + Groq chat with session history and Mem0 context."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from yukti.llm.groq import DEFAULT_SYSTEM

_llm: ChatGroq | None = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0.7,
            max_tokens=256,
        )
    return _llm


def _history_to_messages(history: list[dict]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for item in history:
        role = item.get("role")
        content = item.get("content") or ""
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


def build_messages(
    user_message: str,
    history: list[dict] | None,
    *,
    memory_context: str = "",
) -> list[BaseMessage]:
    system = DEFAULT_SYSTEM
    if memory_context.strip():
        system = f"{system}\n\n{memory_context.strip()}"
    messages: list[BaseMessage] = [SystemMessage(content=system)]
    if history:
        messages.extend(_history_to_messages(history))
    messages.append(HumanMessage(content=user_message))
    return messages


def chat(
    user_message: str,
    history: list[dict] | None = None,
    *,
    memory_context: str = "",
) -> tuple[str, list[dict]]:
    llm = get_llm()
    messages = build_messages(user_message, history, memory_context=memory_context)
    response = llm.invoke(messages)
    reply = (response.content or "").strip()
    new_history = (history or []) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    return reply, new_history


def chat_stream_sync(
    user_message: str,
    history: list[dict] | None = None,
    *,
    memory_context: str = "",
) -> Iterator[str]:
    llm = get_llm()
    messages = build_messages(user_message, history, memory_context=memory_context)
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content


async def chat_stream(
    user_message: str,
    history: list[dict] | None = None,
    *,
    memory_context: str = "",
) -> AsyncIterator[str]:
    llm = get_llm()
    messages = build_messages(user_message, history, memory_context=memory_context)
    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
