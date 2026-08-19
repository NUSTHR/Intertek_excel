import csv
import json
import os
import shutil
import tempfile
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
        self._write_bytes_atomic(path, content)
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
        self._write_text_atomic(
            path,
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
        if target.parent != files_root or target.name != file_id or target.is_symlink():
            raise ValueError("refusing to delete outside storage files root")
        shutil.rmtree(target, ignore_errors=True)

    def delete_version_tree(self, file_id: str, version_id: str) -> None:
        files_root = (self._storage_root / "files").resolve()
        file_root = (files_root / file_id).resolve()
        target = (file_root / version_id).resolve()
        if (
            file_root.parent != files_root
            or file_root.name != file_id
            or target.parent != file_root
            or target.name != version_id
            or target.is_symlink()
        ):
            raise ValueError("refusing to delete outside workbook version directory")
        shutil.rmtree(target, ignore_errors=True)

    def artifact_reference(self, path: Path) -> str:
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_relative_to(self._storage_root):
            raise ValueError("artifact path must stay within storage root")
        return resolved_path.relative_to(self._storage_root).as_posix()

    def resolve_artifact_reference(self, reference: str) -> Path:
        raw_reference = reference.strip()
        if not raw_reference:
            raise ValueError("artifact reference is required")

        normalized_reference = raw_reference.replace("\\", "/")
        if normalized_reference.startswith(("files/", "upload-tasks/")):
            safe_path = self._safe_relative_path(normalized_reference)
            resolved_path = (self._storage_root / safe_path).resolve()
            if not resolved_path.is_relative_to(self._storage_root):
                raise ValueError("artifact reference must stay within storage root")
            return resolved_path

        path = Path(raw_reference).expanduser()
        if path.is_absolute() or self._looks_like_absolute_reference(normalized_reference):
            legacy_relative = self._legacy_storage_relative_reference(normalized_reference)
            if legacy_relative is not None:
                return (self._storage_root / legacy_relative).resolve()
            resolved_path = path.resolve()
            if path.is_absolute() and resolved_path.is_relative_to(self._storage_root):
                return resolved_path
            raise ValueError("absolute artifact reference must stay within storage root")

        raise ValueError("artifact reference must stay within storage root")

    def _version_dir(self, file_id: str, version_id: str) -> Path:
        path = self._storage_root / "files" / file_id / version_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_csv(self, path: Path, rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._temporary_file(path, mode="w", encoding="utf-8-sig", newline="") as (
            csv_file,
            temporary_path,
        ):
            writer = csv.writer(csv_file)
            writer.writerows(rows)
            csv_file.flush()
            os.fsync(csv_file.fileno())
        self._replace_temporary_file(temporary_path, path)

    def _write_bytes_atomic(self, path: Path, content: bytes) -> None:
        with self._temporary_file(path, mode="wb") as (file, temporary_path):
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        self._replace_temporary_file(temporary_path, path)

    def _write_text_atomic(self, path: Path, content: str, *, encoding: str) -> None:
        with self._temporary_file(path, mode="w", encoding=encoding) as (
            file,
            temporary_path,
        ):
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        self._replace_temporary_file(temporary_path, path)

    def _replace_temporary_file(self, temporary_path: Path, path: Path) -> None:
        try:
            temporary_path.replace(path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _temporary_file(self, path: Path, **kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.NamedTemporaryFile(
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            **kwargs,
        )
        temporary_path = Path(temporary.name)
        try:
            return _AtomicFileContext(temporary, temporary_path)
        except Exception:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise

    def _safe_relative_path(self, relative_name: str) -> Path:
        path = Path(relative_name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("relative artifact name must stay within the version directory")
        return path

    def _legacy_storage_relative_reference(self, reference: str) -> Path | None:
        parts = tuple(part for part in reference.split("/") if part)
        for marker in ("files", "upload-tasks"):
            if marker not in parts:
                continue
            marker_index = len(parts) - 1 - parts[::-1].index(marker)
            relative_path = Path(*parts[marker_index:])
            if ".." not in relative_path.parts:
                return relative_path
        return None

    def _looks_like_absolute_reference(self, reference: str) -> bool:
        return reference.startswith("/") or (
            len(reference) >= 2 and reference[1] == ":"
        )


class _AtomicFileContext:
    def __init__(self, file, temporary_path: Path) -> None:
        self.file = file
        self.temporary_path = temporary_path

    def __enter__(self):
        return self.file, self.temporary_path

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.file.close()
        if exc_type is not None:
            self.temporary_path.unlink(missing_ok=True)
