class WorkspaceError(Exception):
    """Base error for expected workspace application failures."""

    code = "WORKSPACE_ERROR"
    retryable = False


class ExcelWorkspaceError(WorkspaceError):
    """Base error for expected Excel Workspace application failures."""


class LlmRequestError(ExcelWorkspaceError):
    code = "LLM_REQUEST_FAILED"
    retryable = True

    def __init__(
        self,
        *,
        stage: str,
        model: str,
        provider: str,
        duration_seconds: float,
        cause: Exception,
    ) -> None:
        self.stage = stage
        self.model = model
        self.provider = provider
        self.duration_seconds = duration_seconds
        super().__init__(
            "LLM request failed "
            f"stage={stage} provider={provider} model={model} "
            f"duration_seconds={duration_seconds:.3f}: {cause}"
        )


class ChatRequestCancelled(ExcelWorkspaceError):
    code = "CHAT_REQUEST_CANCELLED"

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__("chat request was cancelled")


class ChatSessionRevisionConflict(WorkspaceError):
    code = "CHAT_SESSION_REVISION_CONFLICT"
    retryable = True

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(
            "The chat session changed while this answer was being generated. "
            "Retry the request against the latest session state."
        )


class ChatRequestInProgress(WorkspaceError):
    code = "CHAT_REQUEST_IN_PROGRESS"
    retryable = True

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(
            "This chat request is already being processed. Retry shortly with the "
            "same request ID."
        )


class ChatIdempotencyConflict(WorkspaceError):
    code = "CHAT_IDEMPOTENCY_CONFLICT"

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(
            "This request ID was already used for a different chat request."
        )


class FileNameConflictError(ExcelWorkspaceError):
    def __init__(self, display_name: str, file_id: str) -> None:
        super().__init__(f"file '{display_name}' already exists")
        self.display_name = display_name
        self.file_id = file_id


class FileDeleteConfirmationRequiredError(ExcelWorkspaceError):
    def __init__(self, display_name: str, file_id: str) -> None:
        super().__init__(f"deleting '{display_name}' requires explicit confirmation")
        self.display_name = display_name
        self.file_id = file_id


class InvalidLlmModelError(ExcelWorkspaceError):
    def __init__(self, stage: str, model: str) -> None:
        super().__init__(f"unsupported {stage} model '{model}'")
        self.stage = stage
        self.model = model


class AssetNotFoundError(ExcelWorkspaceError):
    pass


class InvalidExcelFileError(ExcelWorkspaceError):
    pass


class VersionActivationError(ExcelWorkspaceError):
    pass


class UploadValidationError(ExcelWorkspaceError):
    pass


class ActiveUploadTaskConflictError(ExcelWorkspaceError):
    code = "ACTIVE_UPLOAD_TASK_EXISTS"
    retryable = True

    def __init__(self, file_id: str, task_id: str) -> None:
        self.file_id = file_id
        self.task_id = task_id
        super().__init__("This file already has an active upload or reparse task.")


class AuthenticationError(ExcelWorkspaceError):
    pass


class RateLimitError(ExcelWorkspaceError):
    code = "RATE_LIMITED"
    retryable = True

    def __init__(self, detail: str, *, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(detail)


class AuthorizationError(ExcelWorkspaceError):
    pass


class LlmResponseFormatError(WorkspaceError):
    code = "LLM_RESPONSE_INVALID"
    retryable = True

    def __init__(self, detail: str = "LLM response was not valid JSON") -> None:
        super().__init__(detail)


class PdfRoutingError(WorkspaceError):
    code = "PDF_ROUTER_INVALID_RESPONSE"
    retryable = True

    def __init__(self, detail: str = "PDF document routing failed. Please retry.") -> None:
        super().__init__(detail)


class PdfSelectionIntegrityError(WorkspaceError):
    code = "PDF_SELECTION_INTEGRITY_ERROR"


class PdfRankingIncomplete(WorkspaceError):
    code = "PDF_RANKING_INCOMPLETE"
    retryable = True


class PdfRetrievalDependencyError(WorkspaceError):
    """A sanitized external retrieval failure with explicit retry semantics."""

    def __init__(
        self,
        detail: str,
        *,
        retryable: bool = True,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.trace_id = trace_id
        super().__init__(detail)


class PdfEmbeddingUnavailable(PdfRetrievalDependencyError):
    code = "PDF_EMBEDDING_UNAVAILABLE"


class PdfVectorStoreUnavailable(PdfRetrievalDependencyError):
    code = "PDF_VECTOR_STORE_UNAVAILABLE"


class PdfRerankerUnavailable(PdfRetrievalDependencyError):
    code = "PDF_RERANKER_UNAVAILABLE"


class PdfAnswerContextTooLarge(WorkspaceError):
    code = "PDF_ANSWER_CONTEXT_TOO_LARGE"

    def __init__(
        self,
        *,
        chunk_count: int,
        character_count: int,
        token_count: int,
        max_chunks: int,
        max_characters: int,
        max_tokens: int,
    ) -> None:
        self.chunk_count = chunk_count
        self.character_count = character_count
        self.token_count = token_count
        self.max_chunks = max_chunks
        self.max_characters = max_characters
        self.max_tokens = max_tokens
        super().__init__(
            "The four selected documents exceed the configured full-document "
            "answer context capacity. No document was truncated."
        )


class UserAlreadyExistsError(ExcelWorkspaceError):
    pass


class PasswordResetTokenError(ExcelWorkspaceError):
    pass
