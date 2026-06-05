class ExcelWorkspaceError(Exception):
    """Base error for expected Excel Workspace application failures."""


class LlmRequestError(ExcelWorkspaceError):
    def __init__(
        self,
        *,
        stage: str,
        model: str,
        duration_seconds: float,
        cause: Exception,
    ) -> None:
        self.stage = stage
        self.model = model
        self.duration_seconds = duration_seconds
        super().__init__(
            "LLM request failed "
            f"stage={stage} model={model} "
            f"duration_seconds={duration_seconds:.3f}: {cause}"
        )


class FileNameConflictError(ExcelWorkspaceError):
    def __init__(self, display_name: str, file_id: str) -> None:
        super().__init__(f"file '{display_name}' already exists")
        self.display_name = display_name
        self.file_id = file_id


class AssetNotFoundError(ExcelWorkspaceError):
    pass


class InvalidExcelFileError(ExcelWorkspaceError):
    pass


class VersionActivationError(ExcelWorkspaceError):
    pass


class UploadValidationError(ExcelWorkspaceError):
    pass
