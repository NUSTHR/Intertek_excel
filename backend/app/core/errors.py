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


class UserAlreadyExistsError(ExcelWorkspaceError):
    pass


class PasswordResetTokenError(ExcelWorkspaceError):
    pass
