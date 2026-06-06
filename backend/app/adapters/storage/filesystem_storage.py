import csv
import json
import shutil
from pathlib import Path


class FilesystemExcelArtifactStorage:
    def __init__(self, storage_root: Path | str) -> None:
        self._storage_root = Path(storage_root).expanduser().resolve()

    def save_original(
        self,
        file_id: str,
        version_id: str,
        original_filename: str,
        content: bytes,
    ) -> Path:
        filename = Path(original_filename).name or "workbook"
        path = self._version_dir(file_id, version_id) / "original" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def write_csv(
        self,
        file_id: str,
        version_id: str,
        sheet_code: str,
        rows: list[list[str]],
    ) -> Path:
        path = self._version_dir(file_id, version_id) / "sheets" / f"{sheet_code}.csv"
        self._write_csv(path, rows)
        return path

    def write_json(
        self,
        file_id: str,
        version_id: str,
        relative_name: str,
        payload: dict,
    ) -> Path:
        path = self._version_dir(file_id, version_id) / self._safe_relative_path(relative_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def write_mapping_csv(
        self,
        file_id: str,
        version_id: str,
        rows: list[list[str]],
    ) -> Path:
        path = self._version_dir(file_id, version_id) / "row_mapping.csv"
        self._write_csv(path, rows)
        return path

    def delete_file_tree(self, file_id: str) -> None:
        files_root = (self._storage_root / "files").resolve()
        target = (files_root / file_id).resolve()
        if not target.is_relative_to(files_root):
            raise ValueError("refusing to delete outside storage files root")
        shutil.rmtree(target, ignore_errors=True)

    def _version_dir(self, file_id: str, version_id: str) -> Path:
        path = self._storage_root / "files" / file_id / version_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_csv(self, path: Path, rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerows(rows)

    def _safe_relative_path(self, relative_name: str) -> Path:
        path = Path(relative_name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("relative artifact name must stay within the version directory")
        return path
