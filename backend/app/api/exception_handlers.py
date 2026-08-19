import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.application.chat.cancellation import ChatRequestCancelledError
from app.core.errors import (
    ActiveUploadTaskConflictError,
    AssetNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ChatIdempotencyConflict,
    ChatRequestCancelled,
    ChatRequestInProgress,
    ChatSessionRevisionConflict,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    InvalidExcelFileError,
    InvalidLlmModelError,
    LlmRequestError,
    LlmResponseFormatError,
    PasswordResetTokenError,
    PdfAnswerContextTooLarge,
    PdfEmbeddingUnavailable,
    PdfRankingIncomplete,
    PdfRerankerUnavailable,
    PdfRoutingError,
    PdfSelectionIntegrityError,
    PdfVectorStoreUnavailable,
    RateLimitError,
    UploadValidationError,
    UserAlreadyExistsError,
    VersionActivationError,
    WorkspaceError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(FileNameConflictError, handle_file_name_conflict)
    app.add_exception_handler(
        ActiveUploadTaskConflictError,
        handle_active_upload_task_conflict,
    )
    app.add_exception_handler(
        FileDeleteConfirmationRequiredError,
        handle_file_delete_confirmation_required,
    )
    app.add_exception_handler(InvalidLlmModelError, handle_invalid_llm_model)
    app.add_exception_handler(ChatRequestCancelled, handle_chat_request_cancelled)
    app.add_exception_handler(ChatRequestInProgress, handle_chat_request_in_progress)
    app.add_exception_handler(ChatIdempotencyConflict, handle_chat_idempotency_conflict)
    app.add_exception_handler(
        ChatSessionRevisionConflict,
        handle_chat_session_revision_conflict,
    )
    app.add_exception_handler(ChatRequestCancelledError, handle_chat_request_cancelled_error)
    app.add_exception_handler(LlmRequestError, handle_llm_request_error)
    app.add_exception_handler(LlmResponseFormatError, handle_llm_response_format_error)
    app.add_exception_handler(PdfRoutingError, handle_pdf_routing_error)
    app.add_exception_handler(
        PdfSelectionIntegrityError,
        handle_pdf_selection_integrity_error,
    )
    for dependency_error in (
        PdfRankingIncomplete,
        PdfEmbeddingUnavailable,
        PdfVectorStoreUnavailable,
        PdfRerankerUnavailable,
    ):
        app.add_exception_handler(
            dependency_error,
            handle_pdf_retrieval_dependency_error,
        )
    app.add_exception_handler(
        PdfAnswerContextTooLarge,
        handle_pdf_answer_context_too_large,
    )
    app.add_exception_handler(AuthenticationError, handle_authentication_error)
    app.add_exception_handler(AuthorizationError, handle_authorization_error)
    app.add_exception_handler(UserAlreadyExistsError, handle_user_already_exists)
    app.add_exception_handler(PasswordResetTokenError, handle_password_reset_token_error)
    app.add_exception_handler(RateLimitError, handle_rate_limit_error)
    app.add_exception_handler(AssetNotFoundError, handle_asset_not_found)
    app.add_exception_handler(InvalidExcelFileError, handle_invalid_excel_file)
    app.add_exception_handler(VersionActivationError, handle_version_activation_error)
    app.add_exception_handler(UploadValidationError, handle_upload_validation_error)
    app.add_exception_handler(WorkspaceError, handle_workspace_error)
    app.add_exception_handler(Exception, handle_unexpected_error)


async def handle_file_name_conflict(
    _request: Request,
    exc: FileNameConflictError,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.CONFLICT,
        {
            "detail": str(exc),
            "display_name": exc.display_name,
            "file_id": exc.file_id,
            "requires_confirmation": True,
        },
    )


async def handle_active_upload_task_conflict(
    _request: Request,
    exc: ActiveUploadTaskConflictError,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.CONFLICT,
        {
            "detail": str(exc),
            "code": exc.code,
            "retryable": exc.retryable,
            "file_id": exc.file_id,
            "task_id": exc.task_id,
        },
    )


async def handle_file_delete_confirmation_required(
    _request: Request,
    exc: FileDeleteConfirmationRequiredError,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.CONFLICT,
        {
            "detail": str(exc),
            "display_name": exc.display_name,
            "file_id": exc.file_id,
            "requires_confirmation": True,
        },
    )


async def handle_invalid_llm_model(
    _request: Request,
    exc: InvalidLlmModelError,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        {
            "detail": str(exc),
            "stage": exc.stage,
            "model": exc.model,
        },
    )


async def handle_llm_request_error(
    _request: Request,
    exc: LlmRequestError,
) -> JSONResponse:
    logger.warning(
        "llm request failed stage=%s provider=%s model=%s duration_seconds=%.3f error=%s",
        exc.stage,
        exc.provider,
        exc.model,
        exc.duration_seconds,
        exc,
    )
    stage_label = _llm_stage_label(exc.stage)
    return _error_response(
        HTTPStatus.BAD_GATEWAY,
        f"The {stage_label} model request failed. Check the selected model or try again shortly.",
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_llm_response_format_error(
    _request: Request,
    exc: LlmResponseFormatError,
) -> JSONResponse:
    logger.warning("llm response format invalid error=%s", exc)
    return _error_response(
        HTTPStatus.BAD_GATEWAY,
        "The model returned an invalid structured response. Please retry.",
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_pdf_routing_error(
    _request: Request,
    exc: PdfRoutingError,
) -> JSONResponse:
    logger.warning("pdf document routing failed error=%s", exc)
    return _error_response(
        HTTPStatus.BAD_GATEWAY,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_pdf_answer_context_too_large(
    _request: Request,
    exc: PdfAnswerContextTooLarge,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        {
            "detail": str(exc),
            "code": exc.code,
            "retryable": False,
            "actual": {
                "chunks": exc.chunk_count,
                "characters": exc.character_count,
                "tokens": exc.token_count,
            },
            "limits": {
                "chunks": exc.max_chunks,
                "characters": exc.max_characters,
                "tokens": exc.max_tokens,
            },
        },
    )


async def handle_pdf_selection_integrity_error(
    _request: Request,
    exc: PdfSelectionIntegrityError,
) -> JSONResponse:
    return _error_response(
        HTTPStatus.CONFLICT,
        str(exc),
        code=exc.code,
        retryable=False,
    )


async def handle_pdf_retrieval_dependency_error(
    _request: Request,
    exc: (
        PdfRankingIncomplete
        | PdfEmbeddingUnavailable
        | PdfVectorStoreUnavailable
        | PdfRerankerUnavailable
    ),
) -> JSONResponse:
    logger.warning("pdf retrieval dependency unavailable code=%s error=%s", exc.code, exc)
    return _error_response(
        HTTPStatus.SERVICE_UNAVAILABLE,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_chat_request_cancelled(
    _request: Request,
    exc: ChatRequestCancelled,
) -> JSONResponse:
    return _json_response(
        499,
        {
            "detail": "Chat request cancelled.",
            "code": exc.code,
            "retryable": False,
            "request_id": exc.request_id,
            "cancelled": True,
        },
    )


async def handle_chat_session_revision_conflict(
    _request: Request,
    exc: ChatSessionRevisionConflict,
) -> JSONResponse:
    return _error_response(
        HTTPStatus.CONFLICT,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_chat_request_in_progress(
    _request: Request,
    exc: ChatRequestInProgress,
) -> JSONResponse:
    return _error_response(
        HTTPStatus.CONFLICT,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
        request_id=exc.request_id,
    )


async def handle_chat_idempotency_conflict(
    _request: Request,
    exc: ChatIdempotencyConflict,
) -> JSONResponse:
    return _error_response(
        HTTPStatus.CONFLICT,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
        request_id=exc.request_id,
    )


async def handle_chat_request_cancelled_error(
    _request: Request,
    exc: ChatRequestCancelledError,
) -> JSONResponse:
    return _json_response(
        499,
        {
            "detail": "Chat request cancelled.",
            "code": "CHAT_REQUEST_CANCELLED",
            "retryable": False,
            "request_id": str(exc),
            "cancelled": True,
        },
    )


async def handle_authentication_error(
    _request: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    return _error_response(HTTPStatus.UNAUTHORIZED, str(exc))


async def handle_authorization_error(
    _request: Request,
    exc: AuthorizationError,
) -> JSONResponse:
    return _error_response(HTTPStatus.FORBIDDEN, str(exc))


async def handle_user_already_exists(
    _request: Request,
    exc: UserAlreadyExistsError,
) -> JSONResponse:
    return _error_response(HTTPStatus.CONFLICT, str(exc))


async def handle_password_reset_token_error(
    _request: Request,
    exc: PasswordResetTokenError,
) -> JSONResponse:
    return _error_response(HTTPStatus.BAD_REQUEST, str(exc))


async def handle_rate_limit_error(
    _request: Request,
    exc: RateLimitError,
) -> JSONResponse:
    return _json_response(
        HTTPStatus.TOO_MANY_REQUESTS,
        {
            "detail": str(exc),
            "retry_after_seconds": exc.retry_after_seconds,
        },
    )


async def handle_asset_not_found(
    _request: Request,
    exc: AssetNotFoundError,
) -> JSONResponse:
    return _error_response(HTTPStatus.NOT_FOUND, str(exc))


async def handle_invalid_excel_file(
    _request: Request,
    exc: InvalidExcelFileError,
) -> JSONResponse:
    return _error_response(HTTPStatus.BAD_REQUEST, str(exc))


async def handle_version_activation_error(
    _request: Request,
    exc: VersionActivationError,
) -> JSONResponse:
    return _error_response(HTTPStatus.CONFLICT, str(exc))


async def handle_upload_validation_error(
    _request: Request,
    exc: UploadValidationError,
) -> JSONResponse:
    return _error_response(HTTPStatus.BAD_REQUEST, str(exc))


async def handle_workspace_error(
    _request: Request,
    exc: WorkspaceError,
) -> JSONResponse:
    return _error_response(
        HTTPStatus.BAD_REQUEST,
        str(exc),
        code=exc.code,
        retryable=exc.retryable,
    )


async def handle_unexpected_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("unhandled application error", exc_info=exc)
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "Something went wrong on the server. Please try again.",
        code="INTERNAL_SERVER_ERROR",
        retryable=True,
    )


def _error_response(
    status_code: HTTPStatus,
    detail: str,
    *,
    code: str = "WORKSPACE_ERROR",
    retryable: bool = False,
    request_id: str | None = None,
) -> JSONResponse:
    return _json_response(
        status_code,
        ErrorResponse(
            detail=detail,
            code=code,
            retryable=retryable,
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


def _json_response(status_code: HTTPStatus | int, content: dict[str, object]) -> JSONResponse:
    resolved_status_code = status_code.value if isinstance(status_code, HTTPStatus) else status_code
    payload = (
        {
            "code": "WORKSPACE_ERROR",
            "retryable": False,
            **content,
        }
        if "detail" in content
        else content
    )
    return JSONResponse(status_code=resolved_status_code, content=payload)


def _llm_stage_label(stage: str) -> str:
    return {
        "document_summary_model": "summary",
        "route_model": "routing",
        "answer_model": "answer",
        "summary": "summary",
        "router": "routing",
        "answer": "answer",
    }.get(stage, "selected")
