import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.application.chat.cancellation import ChatRequestCancelledError
from app.core.errors import (
    AssetNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ChatRequestCancelled,
    ExcelWorkspaceError,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    InvalidExcelFileError,
    InvalidLlmModelError,
    LlmRequestError,
    PasswordResetTokenError,
    UploadValidationError,
    UserAlreadyExistsError,
    VersionActivationError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(FileNameConflictError, handle_file_name_conflict)
    app.add_exception_handler(
        FileDeleteConfirmationRequiredError,
        handle_file_delete_confirmation_required,
    )
    app.add_exception_handler(InvalidLlmModelError, handle_invalid_llm_model)
    app.add_exception_handler(ChatRequestCancelled, handle_chat_request_cancelled)
    app.add_exception_handler(ChatRequestCancelledError, handle_chat_request_cancelled_error)
    app.add_exception_handler(LlmRequestError, handle_llm_request_error)
    app.add_exception_handler(AuthenticationError, handle_authentication_error)
    app.add_exception_handler(AuthorizationError, handle_authorization_error)
    app.add_exception_handler(UserAlreadyExistsError, handle_user_already_exists)
    app.add_exception_handler(PasswordResetTokenError, handle_password_reset_token_error)
    app.add_exception_handler(AssetNotFoundError, handle_asset_not_found)
    app.add_exception_handler(InvalidExcelFileError, handle_invalid_excel_file)
    app.add_exception_handler(VersionActivationError, handle_version_activation_error)
    app.add_exception_handler(UploadValidationError, handle_upload_validation_error)
    app.add_exception_handler(ExcelWorkspaceError, handle_excel_workspace_error)
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
    )


async def handle_chat_request_cancelled(
    _request: Request,
    exc: ChatRequestCancelled,
) -> JSONResponse:
    return _json_response(
        499,
        {
            "detail": "Chat request cancelled.",
            "request_id": exc.request_id,
            "cancelled": True,
        },
    )


async def handle_chat_request_cancelled_error(
    _request: Request,
    exc: ChatRequestCancelledError,
) -> JSONResponse:
    return _json_response(
        499,
        {
            "detail": "Chat request cancelled.",
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


async def handle_excel_workspace_error(
    _request: Request,
    exc: ExcelWorkspaceError,
) -> JSONResponse:
    return _error_response(HTTPStatus.BAD_REQUEST, str(exc))


async def handle_unexpected_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception("unhandled application error", exc_info=exc)
    return _error_response(
        HTTPStatus.INTERNAL_SERVER_ERROR,
        "Something went wrong on the server. Please try again.",
    )


def _error_response(status_code: HTTPStatus, detail: str) -> JSONResponse:
    return _json_response(status_code, ErrorResponse(detail=detail).model_dump())


def _json_response(status_code: HTTPStatus | int, content: dict[str, object]) -> JSONResponse:
    resolved_status_code = status_code.value if isinstance(status_code, HTTPStatus) else status_code
    return JSONResponse(status_code=resolved_status_code, content=content)


def _llm_stage_label(stage: str) -> str:
    return {
        "document_summary_model": "summary",
        "route_model": "routing",
        "answer_model": "answer",
        "summary": "summary",
        "router": "routing",
        "answer": "answer",
    }.get(stage, "selected")
