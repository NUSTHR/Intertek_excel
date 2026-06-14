from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.api.dependencies import get_excel_repository
from app.core.config import get_settings
from app.main import app


def test_health_and_readiness_endpoints(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
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
    assert ready_response.json() == {
        "status": "ready",
        "checks": {"storage": "ok", "database": "ok"},
    }


class _temporary_settings_env:
    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path = tmp_path
        self._original_database_path: str | None = None
        self._original_storage_root: str | None = None

    def __enter__(self) -> None:
        import os

        self._original_database_path = os.environ.get("EXCEL_DATABASE_PATH")
        self._original_storage_root = os.environ.get("EXCEL_STORAGE_ROOT")
        os.environ["EXCEL_DATABASE_PATH"] = str(self._tmp_path / "ready.sqlite3")
        os.environ["EXCEL_STORAGE_ROOT"] = str(self._tmp_path / "storage")

    def __exit__(self, *_args: object) -> None:
        self._restore_env("EXCEL_DATABASE_PATH", self._original_database_path)
        self._restore_env("EXCEL_STORAGE_ROOT", self._original_storage_root)

    def _restore_env(self, key: str, value: str | None) -> None:
        import os

        if value is None:
            os.environ.pop(key, None)
            return
        os.environ[key] = value
