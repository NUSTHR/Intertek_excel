import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, document_summaries, excel_assets, health
from app.api.schemas import ErrorResponse
from app.core.config import get_settings
from app.core.errors import (
    AssetNotFoundError,
    ExcelWorkspaceError,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    InvalidExcelFileError,
    InvalidLlmModelError,
    LlmRequestError,
    UploadValidationError,
    VersionActivationError,
)

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.app_cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FileNameConflictError)
async def handle_file_name_conflict(
    _request: Request,
    exc: FileNameConflictError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": str(exc),
            "display_name": exc.display_name,
            "file_id": exc.file_id,
            "requires_confirmation": True,
        },
    )


@app.exception_handler(FileDeleteConfirmationRequiredError)
async def handle_file_delete_confirmation_required(
    _request: Request,
    exc: FileDeleteConfirmationRequiredError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": str(exc),
            "display_name": exc.display_name,
            "file_id": exc.file_id,
            "requires_confirmation": True,
        },
    )


@app.exception_handler(InvalidLlmModelError)
async def handle_invalid_llm_model(
    _request: Request,
    exc: InvalidLlmModelError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "stage": exc.stage,
            "model": exc.model,
        },
    )


@app.exception_handler(LlmRequestError)
async def handle_llm_request_error(
    _request: Request,
    exc: LlmRequestError,
) -> JSONResponse:
    logger.warning(
        "llm request failed stage=%s model=%s duration_seconds=%.3f",
        exc.stage,
        exc.model,
        exc.duration_seconds,
    )
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(
            detail="The model request failed. Please try again shortly."
        ).model_dump(),
    )


@app.exception_handler(AssetNotFoundError)
async def handle_asset_not_found(
    _request: Request,
    exc: AssetNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(InvalidExcelFileError)
async def handle_invalid_excel_file(
    _request: Request,
    exc: InvalidExcelFileError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(VersionActivationError)
async def handle_version_activation_error(
    _request: Request,
    exc: VersionActivationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(UploadValidationError)
async def handle_upload_validation_error(
    _request: Request,
    exc: UploadValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(ExcelWorkspaceError)
async def handle_excel_workspace_error(
    _request: Request,
    exc: ExcelWorkspaceError,
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(detail=str(exc)).model_dump(),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("unhandled application error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="Something went wrong on the server. Please try again."
        ).model_dump(),
    )


app.include_router(health.router)
app.include_router(excel_assets.router)
app.include_router(document_summaries.router)
app.include_router(chat.router)
