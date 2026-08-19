from pathlib import Path

from app.adapters.health.disk import DiskRuntimeInspection
from app.adapters.repositories.sqlite.health import SQLiteRuntimeInspection
from app.adapters.repositories.sqlite.migrations import SQLiteSchemaInspection
from app.application.operational.readiness import (
    ReadinessService,
    WorkerReadinessProbe,
)
from app.application.operational.worker_status import WorkerRuntimeStatus
from app.core.config import Settings
from app.ports.pdf_parser import PdfParserRuntimeStatus
from app.ports.pdf_vector_index import PdfVectorQueueInspection


class _DiskProbe:
    def __init__(self, inspection: DiskRuntimeInspection) -> None:
        self._inspection = inspection

    def inspect(self) -> DiskRuntimeInspection:
        return self._inspection


def test_readiness_reports_migration_mismatch_without_mutating_database(tmp_path: Path) -> None:
    schema = _schema(missing_versions=(28,), applied_version=27)
    service = _service(tmp_path, schema=schema)

    result = service.inspect()

    assert result.status == "not_ready"
    assert result.checks["database"].status == "ok"
    assert result.checks["migrations"].status == "unavailable"
    assert result.checks["migrations"].metadata["current_version"] == 27
    assert result.checks["migrations"].metadata["expected_version"] == 28


def test_readiness_treats_disabled_workers_and_inactive_mineru_as_non_blocking(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, parser_backend="fake")

    result = service.inspect()

    assert result.status == "ready"
    assert result.checks["mineru"].status == "disabled"
    assert result.checks["excel_upload_worker"].status == "disabled"


def test_readiness_fails_when_enabled_worker_is_not_running(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        workers={
            "excel_upload_worker": WorkerReadinessProbe(
                enabled=True,
                status_provider=lambda: WorkerRuntimeStatus(
                    running=False,
                    state="stopped",
                    started_at=None,
                    last_poll_at=None,
                    last_success_at=None,
                    last_failure_at=None,
                    current_task_started_at=None,
                    consecutive_loop_failures=0,
                ),
                idle_stale_seconds=5,
                busy_stale_seconds=60,
            )
        },
    )

    result = service.inspect()

    assert result.status == "not_ready"
    assert result.checks["excel_upload_worker"].message == "worker_not_running"


def test_readiness_reports_critical_disk_space(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        disk_inspection=DiskRuntimeInspection(
            accessible=True,
            writable=True,
            free_bytes=1,
            free_percent=1.0,
        ),
    )

    result = service.inspect()

    assert result.status == "not_ready"
    assert result.checks["storage"].status == "ok"
    assert result.checks["disk"].message == "disk_space_critical"


def test_readiness_contains_worker_probe_failures(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        workers={
            "excel_upload_worker": WorkerReadinessProbe(
                enabled=True,
                status_provider=_raise_probe_error,
                idle_stale_seconds=5,
                busy_stale_seconds=60,
            )
        },
    )

    result = service.inspect()

    assert result.status == "not_ready"
    assert result.checks["excel_upload_worker"].message == "worker_probe_failed"


def test_readiness_contains_core_probe_failures(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        sqlite_inspector=_raise_probe_error,
        mineru_inspector=_raise_probe_error,
    )

    result = service.inspect()

    assert result.status == "not_ready"
    assert result.checks["database"].message == "database_probe_failed"
    assert result.checks["migrations"].message == "migration_probe_failed"
    assert result.checks["mineru"].message == "mineru_probe_failed"


def test_readiness_reports_vector_dead_letters_as_degraded(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        vector_enabled=True,
        vector_queue_inspector=lambda: PdfVectorQueueInspection(
            pending_count=1,
            running_count=0,
            retry_wait_count=0,
            dead_letter_count=2,
            expired_running_count=0,
            due_retry_count=0,
            oldest_active_at="2026-08-14T00:00:00+00:00",
        ),
    )

    result = service.inspect()

    assert result.status == "degraded"
    assert result.checks["pdf_vector_queue"].message == (
        "vector_queue_contains_dead_letters"
    )
    assert result.checks["pdf_vector_queue"].metadata["dead_letter_count"] == 2


def _service(
    tmp_path: Path,
    *,
    schema: SQLiteSchemaInspection | None = None,
    parser_backend: str = "mineru",
    workers: dict[str, WorkerReadinessProbe] | None = None,
    disk_inspection: DiskRuntimeInspection | None = None,
    sqlite_inspector=None,
    mineru_inspector=None,
    vector_enabled: bool = False,
    vector_queue_inspector=None,
) -> ReadinessService:
    settings = Settings(
        _env_file=None,
        excel_storage_root=str(tmp_path),
        pdf_parser_backend=parser_backend,
        readiness_disk_warning_free_bytes=100,
        readiness_disk_critical_free_bytes=10,
        readiness_disk_warning_free_percent=10,
        readiness_disk_critical_free_percent=3,
        pdf_vector_search_enabled=vector_enabled,
    )
    resolved_schema = schema or _schema()
    resolved_workers = workers or {
        "excel_upload_worker": WorkerReadinessProbe(
            enabled=False,
            status_provider=_unused_worker_status,
            idle_stale_seconds=5,
            busy_stale_seconds=60,
        )
    }
    return ReadinessService(
        settings=settings,
        sqlite_inspector=sqlite_inspector
        or (
            lambda: SQLiteRuntimeInspection(
                database_available=True,
                schema=resolved_schema,
            )
        ),
        mineru_inspector=mineru_inspector
        or (
            lambda: PdfParserRuntimeStatus(
                backend="mineru",
                available=True,
                version="3.4.0",
            )
        ),
        workers=resolved_workers,
        disk_probe=_DiskProbe(
            disk_inspection
            or DiskRuntimeInspection(
                accessible=True,
                writable=True,
                free_bytes=1_000,
                free_percent=50.0,
            )
        ),
        vector_queue_inspector=vector_queue_inspector,
        vector_store_inspector=(lambda: None) if vector_enabled else None,
    )


def _schema(
    *,
    missing_versions: tuple[int, ...] = (),
    applied_version: int = 28,
) -> SQLiteSchemaInspection:
    return SQLiteSchemaInspection(
        migration_table_exists=True,
        expected_version=28,
        applied_version=applied_version,
        missing_versions=missing_versions,
        unknown_versions=(),
        checksum_mismatches=(),
    )


def _unused_worker_status() -> WorkerRuntimeStatus:
    raise AssertionError("disabled worker status must not be inspected")


def _raise_probe_error():
    raise RuntimeError("probe failed")
