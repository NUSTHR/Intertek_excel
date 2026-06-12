from dataclasses import dataclass

from app.domain.models import UserRole


@dataclass(frozen=True)
class FileAccessContext:
    user_id: str
    role: UserRole

    @property
    def can_manage_files(self) -> bool:
        return self.role == UserRole.ADMIN
