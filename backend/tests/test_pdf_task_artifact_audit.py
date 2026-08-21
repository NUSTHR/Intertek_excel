import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from scripts.audit_pdf_task_artifacts import audit_task_artifacts


def test_task_artifact_audit_requires_retention_and_explicit_delete(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "excel.sqlite3"
    storage_root = tmp_path / "storage"
    SQLiteExcelAssetRepository(database_path).initialize()
    old_claim = (
        storage_root
        / "pdf-knowledge/files/orphan-file/task-artifacts/orphan-task/old-claim"
    )
    recent_claim = (
        storage_root
        / "pdf-knowledge/files/orphan-file/task-artifacts/orphan-task/recent-claim"
    )
    old_claim.mkdir(parents=True)
    recent_claim.mkdir(parents=True)
    (old_claim / "artifact.md").write_text("old", encoding="utf-8")
    (recent_claim / "artifact.md").write_text("recent", encoding="utf-8")
    old_timestamp = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    os.utime(old_claim, (old_timestamp, old_timestamp))

    report = audit_task_artifacts(
        database_path=database_path,
        storage_root=storage_root,
        retention_days=7,
    )

    assert report["candidate_count"] == 1
    assert report["deleted_count"] == 0
    assert old_claim.exists()
    assert recent_claim.exists()

    deleted_report = audit_task_artifacts(
        database_path=database_path,
        storage_root=storage_root,
        retention_days=7,
        delete=True,
    )

    assert deleted_report["deleted_count"] == 1
    assert not old_claim.exists()
    assert recent_claim.exists()
