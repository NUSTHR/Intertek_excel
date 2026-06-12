from dataclasses import dataclass
from pathlib import Path

from app.core.errors import UploadValidationError


@dataclass(frozen=True)
class ExcelUploadPolicy:
    supported_extensions: tuple[str, ...]
    max_bytes: int

    def validate(self, filename: str, content: bytes) -> None:
        extension = Path(filename).suffix.lower()
        if extension not in self.supported_extensions:
            raise UploadValidationError(
                "unsupported Excel file extension; supported extensions are "
                f"{self.supported_extension_label}"
            )
        if not content:
            raise UploadValidationError("uploaded Excel file is empty")
        if len(content) > self.max_bytes:
            raise UploadValidationError(
                f"uploaded Excel file exceeds the {self.max_bytes} byte limit"
            )

    @property
    def supported_extension_label(self) -> str:
        if len(self.supported_extensions) <= 1:
            return "".join(self.supported_extensions)
        return f"{', '.join(self.supported_extensions[:-1])}, and {self.supported_extensions[-1]}"
