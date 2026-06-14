from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import (
    SAFE_HTTP_METHODS,
    AuthCredentialsDependency,
    get_auth_service,
    get_current_user,
)
from app.api.schemas import (
    AuthResponse,
    LoginRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.application.auth.service import AuthResult, AuthService
from app.core.auth import new_secret_token
from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/api/auth", tags=["auth"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post("/register", response_model=AuthResponse)
def register(
    request: RegisterRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthResponse:
    result = service.register(request.email, request.password)
    _set_auth_cookies(response, result)
    return _to_auth_response(result)


@router.post("/login", response_model=AuthResponse)
def login(
    request: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthResponse:
    result = service.login(request.email, request.password)
    _set_auth_cookies(response, result)
    return _to_auth_response(result)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUserDependency) -> UserResponse:
    return _to_user_response(user)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    credentials: AuthCredentialsDependency,
) -> None:
    if credentials is not None:
        service.logout(credentials.credentials)
    else:
        _require_cookie_csrf(request)
        token = request.cookies.get(get_settings().auth_cookie_name)
        if token is not None:
            service.logout(token)
    _clear_auth_cookies(response)


@router.post("/password/forgot", response_model=PasswordResetResponse)
def forgot_password(
    request: PasswordResetRequest,
    service: AuthServiceDependency,
) -> PasswordResetResponse:
    result = service.request_password_reset(request.email)
    return PasswordResetResponse(
        email=result.email,
        reset_token=result.reset_token,
        expires_at=result.expires_at,
    )


@router.post("/password/reset", response_model=AuthResponse)
def reset_password(
    request: ResetPasswordRequest,
    response: Response,
    service: AuthServiceDependency,
) -> AuthResponse:
    result = service.reset_password(request.token, request.new_password)
    _set_auth_cookies(response, result)
    return _to_auth_response(result)


def _set_auth_cookies(response: Response, result: AuthResult) -> None:
    settings = get_settings()
    csrf_token = new_secret_token()
    max_age = max(1, settings.auth_session_ttl_hours * 60 * 60)
    cookie_samesite = settings.auth_cookie_samesite.strip().lower()
    response.set_cookie(
        settings.auth_cookie_name,
        result.access_token,
        max_age=max_age,
        expires=result.expires_at,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=cookie_samesite,
        path="/",
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        expires=result.expires_at,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=cookie_samesite,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    cookie_samesite = settings.auth_cookie_samesite.strip().lower()
    response.delete_cookie(
        settings.auth_cookie_name,
        secure=settings.auth_cookie_secure,
        samesite=cookie_samesite,
        path="/",
    )
    response.delete_cookie(
        settings.auth_csrf_cookie_name,
        secure=settings.auth_cookie_secure,
        samesite=cookie_samesite,
        path="/",
    )


def _require_cookie_csrf(request: Request) -> None:
    if request.method.upper() in SAFE_HTTP_METHODS:
        return
    settings = get_settings()
    if settings.auth_cookie_name not in request.cookies:
        return
    csrf_cookie = request.cookies.get(settings.auth_csrf_cookie_name)
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise AuthenticationError("csrf token is invalid or missing")


def _to_auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        user=_to_user_response(result.user),
        access_token=result.access_token,
        expires_at=result.expires_at,
    )


def _to_user_response(user: AuthenticatedUser) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role.value,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
