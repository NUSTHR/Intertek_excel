class ExcelWorkspaceError(Exception):
    """Base error for expected Excel Workspace application failures."""


class LlmRequestError(ExcelWorkspaceError):
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
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__("chat request was cancelled")


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


class AuthorizationError(ExcelWorkspaceError):
    pass


class UserAlreadyExistsError(ExcelWorkspaceError):
    pass


class PasswordResetTokenError(ExcelWorkspaceError):
    pass
