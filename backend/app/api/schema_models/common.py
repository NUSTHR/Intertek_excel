from pydantic import BaseModel, Field


class ChatSessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: str
    updated_at: str
    title: str
    pinned_at: str | None = None
    status: str


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse] = Field(default_factory=list)


class RenameChatSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class PinChatSessionRequest(BaseModel):
    pinned: bool
