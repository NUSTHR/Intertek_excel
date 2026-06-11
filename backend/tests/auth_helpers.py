from app.domain.models import AuthenticatedUser, UserRole


def admin_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user_admin_test",
        email="969348539@qq.com",
        role=UserRole.ADMIN,
        created_at="2026-01-01T00:00:00+00:00",
    )


def member_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user_member_test",
        email="member@example.com",
        role=UserRole.MEMBER,
        created_at="2026-01-01T00:00:00+00:00",
    )
