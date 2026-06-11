from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
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
from app.domain.models import AuthenticatedUser

router = APIRouter(prefix="/api/auth", tags=["auth"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.post("/register", response_model=AuthResponse)
def register(
    request: RegisterRequest,
    service: AuthServiceDependency,
) -> AuthResponse:
    return _to_auth_response(service.register(request.email, request.password))


@router.post("/login", response_model=AuthResponse)
def login(
    request: LoginRequest,
    service: AuthServiceDependency,
) -> AuthResponse:
    return _to_auth_response(service.login(request.email, request.password))


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUserDependency) -> UserResponse:
    return _to_user_response(user)


@router.post("/logout", status_code=204)
def logout(
    service: AuthServiceDependency,
    credentials: AuthCredentialsDependency,
) -> None:
    if credentials is not None:
        service.logout(credentials.credentials)


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
    service: AuthServiceDependency,
) -> AuthResponse:
    return _to_auth_response(
        service.reset_password(request.token, request.new_password)
    )


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
