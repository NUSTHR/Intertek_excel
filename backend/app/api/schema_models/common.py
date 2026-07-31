from pydantic import BaseModel, Field


class ChatSessionResponse(BaseModel):
    session_id: str
    user_id: str
    created_at: str
    updated_at: str
    title: str
    pinned_at: str | None = None
    status: str
    context_file_ids: list[str] = Field(default_factory=list)
    revision: int = 0


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse] = Field(default_factory=list)


class RenameChatSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    expected_revision: int | None = Field(default=None, ge=0)


class PinChatSessionRequest(BaseModel):
    pinned: bool
    expected_revision: int | None = Field(default=None, ge=0)
