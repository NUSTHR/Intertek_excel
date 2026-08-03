from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_readiness_service
from app.api.schemas import (
    HealthResponse,
    ReadinessCheckDetailResponse,
    ReadinessResponse,
)
from app.application.operational import ReadinessService

router = APIRouter(tags=["health"])
ReadinessServiceDependency = Annotated[ReadinessService, Depends(get_readiness_service)]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def ready(service: ReadinessServiceDependency) -> ReadinessResponse | JSONResponse:
    result = service.inspect()
    response = ReadinessResponse(
        status=result.status,
        checks={name: check.status for name, check in result.checks.items()},
        details={
            name: ReadinessCheckDetailResponse(
                status=check.status,
                required=check.required,
                message=check.message,
                metadata=check.metadata,
            )
            for name, check in result.checks.items()
        },
    )
    if result.is_ready:
        return response
    return JSONResponse(status_code=503, content=response.model_dump())
