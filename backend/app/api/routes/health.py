from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.api.dependencies import get_excel_repository
from app.api.schemas import HealthResponse, ReadinessResponse
from app.core.config import get_settings

router = APIRouter(tags=["health"])
RepositoryDependency = Annotated[SQLiteExcelAssetRepository, Depends(get_excel_repository)]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def ready(repository: RepositoryDependency) -> ReadinessResponse | JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        checks["storage"] = "ok" if settings.storage_root.is_dir() else "unavailable"
    except OSError:
        checks["storage"] = "unavailable"

    try:
        repository.initialize()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    if all(value == "ok" for value in checks.values()):
        return ReadinessResponse(status="ready", checks=checks)
    return JSONResponse(
        status_code=503,
        content=ReadinessResponse(status="not_ready", checks=checks).model_dump(),
    )
