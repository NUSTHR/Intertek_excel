from fastapi import APIRouter

from app.api.schemas import WorkspaceConfigResponse, WorkspaceUploadConfigResponse
from app.core.config import get_settings

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/config", response_model=WorkspaceConfigResponse)
def get_workspace_config() -> WorkspaceConfigResponse:
    settings = get_settings()
    return WorkspaceConfigResponse(
        upload=WorkspaceUploadConfigResponse(
            max_bytes=settings.excel_max_upload_bytes,
            supported_extensions=list(settings.supported_excel_extensions),
        )
    )
