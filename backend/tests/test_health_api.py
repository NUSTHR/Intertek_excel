from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.repositories.sqlite_repository import (
    SCHEMA_MIGRATIONS,
    SQLiteExcelAssetRepository,
)
from app.api.dependencies import get_excel_repository
from app.core.config import get_settings
from app.main import app


def test_health_and_readiness_endpoints(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    repository.initialize()
    (tmp_path / "storage").mkdir()
    app.dependency_overrides[get_excel_repository] = lambda: repository
    get_settings.cache_clear()
    try:
        with _temporary_settings_env(tmp_path):
            get_settings.cache_clear()
            with TestClient(app) as client:
                health_response = client.get("/health")
                ready_response = client.get("/ready")
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    payload = ready_response.json()
    assert payload["status"] == "ready"
    assert payload["checks"] == {
        "storage": "ok",
        "disk": "ok",
        "database": "ok",
        "migrations": "ok",
        "mineru": "ok",
        "excel_upload_worker": "ok",
        "pdf_upload_worker": "ok",
        "pdf_summary_worker": "ok",
    }
    assert payload["details"]["migrations"]["metadata"] == {
        "migration_table_exists": True,
        "current_version": max(migration.version for migration in SCHEMA_MIGRATIONS),
        "expected_version": max(migration.version for migration in SCHEMA_MIGRATIONS),
        "missing_count": 0,
        "unknown_count": 0,
        "checksum_mismatch_count": 0,
    }
    assert payload["details"]["mineru"]["metadata"]["version"] == "mineru, version 3.4.0"


class _temporary_settings_env:
    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path
        self._original_values: dict[str, str | None] = {}

    def __enter__(self) -> None:
        import os

        mineru_command = self._tmp_path / "mineru"
        mineru_command.write_text(
            "#!/bin/sh\nprintf 'mineru, version 3.4.0\\n'\n",
            encoding="utf-8",
        )
        mineru_command.chmod(0o755)
        overrides = {
            "EXCEL_DATABASE_PATH": str(self._tmp_path / "ready.sqlite3"),
            "EXCEL_STORAGE_ROOT": str(self._tmp_path / "storage"),
            "PDF_PARSER_BACKEND": "mineru",
            "MINERU_COMMAND": str(mineru_command),
        }
        self._original_values = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)

    def __exit__(self, *_args: object) -> None:
        for key, value in self._original_values.items():
            self._restore_env(key, value)

    def _restore_env(self, key: str, value: str | None) -> None:
        import os

        if value is None:
            os.environ.pop(key, None)
            return
        os.environ[key] = value
