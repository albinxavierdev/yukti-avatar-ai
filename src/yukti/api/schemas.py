"""API request/response models."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    voice: str = "F2"
    lang: str = "en"


class ChatResponse(BaseModel):
    reply: str
    audio_base64: str
    session_id: str


class SessionSummary(BaseModel):
    id: str
    title: str
    updated_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
