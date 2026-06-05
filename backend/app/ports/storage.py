from pathlib import Path
from typing import Protocol


class ExcelArtifactStorage(Protocol):
    def save_original(
        self,
        file_id: str,
        version_id: str,
        original_filename: str,
        content: bytes,
    ) -> Path:
        ...

    def write_csv(
        self,
        file_id: str,
        version_id: str,
        sheet_code: str,
        rows: list[list[str]],
    ) -> Path:
        ...

    def write_json(
        self,
        file_id: str,
        version_id: str,
        relative_name: str,
        payload: dict,
    ) -> Path:
        ...

    def write_mapping_csv(
        self,
        file_id: str,
        version_id: str,
        rows: list[list[str]],
    ) -> Path:
        ...

    def delete_file_tree(self, file_id: str) -> None:
        ...
