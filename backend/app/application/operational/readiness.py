from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.adapters.health import DiskRuntimeProbe
from app.adapters.repositories.sqlite.health import SQLiteRuntimeInspection
from app.application.operational.worker_status import WorkerRuntimeStatus
from app.core.config import Settings
from app.ports.pdf_parser import PdfParserRuntimeStatus
from app.ports.pdf_vector_index import PdfVectorQueueInspection

CHECK_OK = "ok"
CHECK_WARNING = "warning"
CHECK_UNAVAILABLE = "unavailable"
CHECK_DISABLED = "disabled"


@dataclass(frozen=True)
class ReadinessCheck:
    status: str
    required: bool
    message: str = ""
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessResult:
    status: str
    checks: dict[str, ReadinessCheck]

    @property
    def is_ready(self) -> bool:
        return self.status != "not_ready"


@dataclass(frozen=True)
class WorkerReadinessProbe:
    enabled: bool
    status_provider: Callable[[], WorkerRuntimeStatus]
    idle_stale_seconds: float
    busy_stale_seconds: float


class ReadinessService:
    def __init__(
        self,
        *,
        settings: Settings,
        sqlite_inspector: Callable[[], SQLiteRuntimeInspection],
        mineru_inspector: Callable[[], PdfParserRuntimeStatus],
        workers: dict[str, WorkerReadinessProbe],
        disk_probe: DiskRuntimeProbe | None = None,
        vector_queue_inspector: Callable[[], PdfVectorQueueInspection] | None = None,
        vector_store_inspector: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._sqlite_inspector = sqlite_inspector
        self._mineru_inspector = mineru_inspector
        self._workers = workers
        self._disk_probe = disk_probe or DiskRuntimeProbe(settings.storage_root)
        self._vector_queue_inspector = vector_queue_inspector
        self._vector_store_inspector = vector_store_inspector

    def inspect(self) -> ReadinessResult:
        checks: dict[str, ReadinessCheck] = {}
        try:
            self._inspect_disk(checks)
        except Exception:
            checks["storage"] = _failed_probe("storage_probe_failed")
            checks["disk"] = _failed_probe("disk_probe_failed")
        try:
            self._inspect_sqlite(checks)
        except Exception:
            checks["database"] = _failed_probe("database_probe_failed")
            checks["migrations"] = _failed_probe("migration_probe_failed")
        try:
            self._inspect_mineru(checks)
        except Exception:
            checks["mineru"] = _failed_probe("mineru_probe_failed")
        for name, probe in self._workers.items():
            try:
                checks[name] = self._inspect_worker(probe)
            except Exception:
                checks[name] = _failed_probe(
                    "worker_probe_failed",
                    metadata={"enabled": probe.enabled},
                )
        if self._settings.pdf_vector_indexing_active:
            try:
                checks["pdf_vector_store"] = self._inspect_vector_store()
            except Exception:
                checks["pdf_vector_store"] = ReadinessCheck(
                    status=(
                        CHECK_UNAVAILABLE
                        if self._settings.pdf_vector_ranking_active
                        else CHECK_WARNING
                    ),
                    required=self._settings.pdf_vector_ranking_active,
                    message="vector_store_probe_failed",
                )
            try:
                checks["pdf_vector_queue"] = self._inspect_vector_queue()
            except Exception:
                checks["pdf_vector_queue"] = _failed_probe(
                    "vector_queue_probe_failed"
                )

        required_failure = any(
            check.required and check.status == CHECK_UNAVAILABLE
            for check in checks.values()
        )
        has_warning = any(check.status == CHECK_WARNING for check in checks.values())
        status = "not_ready" if required_failure else "degraded" if has_warning else "ready"
        return ReadinessResult(status=status, checks=checks)

    def _inspect_vector_store(self) -> ReadinessCheck:
        if self._vector_store_inspector is None:
            raise RuntimeError("PDF vector store inspector is not configured")
        self._vector_store_inspector()
        return ReadinessCheck(
            status=CHECK_OK,
            required=self._settings.pdf_vector_ranking_active,
        )

    def _inspect_vector_queue(self) -> ReadinessCheck:
        if self._vector_queue_inspector is None:
            raise RuntimeError("PDF vector queue inspector is not configured")
        inspection = self._vector_queue_inspector()
        metadata: dict[str, str | int | float | bool | None] = {
            "pending_count": inspection.pending_count,
            "running_count": inspection.running_count,
            "retry_wait_count": inspection.retry_wait_count,
            "dead_letter_count": inspection.dead_letter_count,
            "expired_running_count": inspection.expired_running_count,
            "due_retry_count": inspection.due_retry_count,
            "oldest_active_at": inspection.oldest_active_at,
        }
        if inspection.expired_running_count or inspection.due_retry_count:
            return ReadinessCheck(
                status=CHECK_WARNING,
                required=True,
                message="vector_queue_recovery_pending",
                metadata=metadata,
            )
        if inspection.dead_letter_count:
            return ReadinessCheck(
                status=CHECK_WARNING,
                required=True,
                message="vector_queue_contains_dead_letters",
                metadata=metadata,
            )
        return ReadinessCheck(
            status=CHECK_OK,
            required=True,
            metadata=metadata,
        )

    def _inspect_disk(self, checks: dict[str, ReadinessCheck]) -> None:
        inspection = self._disk_probe.inspect()
        storage_ok = inspection.accessible and inspection.writable
        checks["storage"] = ReadinessCheck(
            status=CHECK_OK if storage_ok else CHECK_UNAVAILABLE,
            required=True,
            message="" if storage_ok else (inspection.error_code or "storage_unavailable"),
        )
        if not inspection.accessible:
            checks["disk"] = ReadinessCheck(
                status=CHECK_UNAVAILABLE,
                required=True,
                message=inspection.error_code or "disk_unavailable",
            )
            return

        metadata: dict[str, str | int | float | bool | None] = {
            "free_bytes": inspection.free_bytes,
            "free_percent": inspection.free_percent,
        }
        critical = (
            inspection.free_bytes < self._settings.readiness_disk_critical_free_bytes
            or inspection.free_percent < self._settings.readiness_disk_critical_free_percent
        )
        warning = (
            inspection.free_bytes < self._settings.readiness_disk_warning_free_bytes
            or inspection.free_percent < self._settings.readiness_disk_warning_free_percent
        )
        if critical:
            checks["disk"] = ReadinessCheck(
                status=CHECK_UNAVAILABLE,
                required=True,
                message="disk_space_critical",
                metadata=metadata,
            )
        elif warning:
            checks["disk"] = ReadinessCheck(
                status=CHECK_WARNING,
                required=True,
                message="disk_space_low",
                metadata=metadata,
            )
        else:
            checks["disk"] = ReadinessCheck(
                status=CHECK_OK,
                required=True,
                metadata=metadata,
            )

    def _inspect_sqlite(self, checks: dict[str, ReadinessCheck]) -> None:
        inspection = self._sqlite_inspector()
        checks["database"] = ReadinessCheck(
            status=CHECK_OK if inspection.database_available else CHECK_UNAVAILABLE,
            required=True,
            message="" if inspection.database_available else (
                inspection.error_code or "database_unavailable"
            ),
        )
        schema = inspection.schema
        if not inspection.database_available or schema is None:
            checks["migrations"] = ReadinessCheck(
                status=CHECK_UNAVAILABLE,
                required=True,
                message="schema_unavailable",
            )
            return
        checks["migrations"] = ReadinessCheck(
            status=CHECK_OK if schema.is_ready else CHECK_UNAVAILABLE,
            required=True,
            message="" if schema.is_ready else "schema_mismatch",
            metadata={
                "migration_table_exists": schema.migration_table_exists,
                "current_version": schema.applied_version,
                "expected_version": schema.expected_version,
                "missing_count": len(schema.missing_versions),
                "unknown_count": len(schema.unknown_versions),
                "checksum_mismatch_count": len(schema.checksum_mismatches),
            },
        )

    def _inspect_mineru(self, checks: dict[str, ReadinessCheck]) -> None:
        backend = self._settings.pdf_parser_backend.strip().lower()
        if backend != "mineru":
            checks["mineru"] = ReadinessCheck(
                status=CHECK_DISABLED,
                required=False,
                message="active_parser_is_not_mineru",
                metadata={"backend": backend or "unknown"},
            )
            return
        status = self._mineru_inspector()
        checks["mineru"] = ReadinessCheck(
            status=CHECK_OK if status.available else CHECK_UNAVAILABLE,
            required=True,
            message="" if status.available else "mineru_unavailable",
            metadata={
                "backend": status.backend,
                "version": status.version,
            },
        )

    def _inspect_worker(self, probe: WorkerReadinessProbe) -> ReadinessCheck:
        if not probe.enabled:
            return ReadinessCheck(
                status=CHECK_DISABLED,
                required=False,
                message="worker_disabled",
                metadata={"enabled": False, "running": False},
            )
        status = probe.status_provider()
        metadata: dict[str, str | int | float | bool | None] = {
            "enabled": True,
            "running": status.running,
            "state": status.state,
            "started_at": status.started_at,
            "last_poll_at": status.last_poll_at,
            "last_success_at": status.last_success_at,
            "last_failure_at": status.last_failure_at,
            "current_task_started_at": status.current_task_started_at,
            "consecutive_loop_failures": status.consecutive_loop_failures,
        }
        if not status.running or status.state in {"dead", "stopped"}:
            return ReadinessCheck(
                status=CHECK_UNAVAILABLE,
                required=True,
                message="worker_not_running",
                metadata=metadata,
            )
        timestamp = (
            status.current_task_started_at
            if status.state == "busy"
            else status.last_poll_at
        )
        stale_after = (
            probe.busy_stale_seconds
            if status.state == "busy"
            else probe.idle_stale_seconds
        )
        if timestamp and _age_seconds(timestamp) > stale_after:
            return ReadinessCheck(
                status=CHECK_UNAVAILABLE,
                required=True,
                message="worker_heartbeat_stale",
                metadata=metadata,
            )
        if status.consecutive_loop_failures >= 3:
            return ReadinessCheck(
                status=CHECK_WARNING,
                required=True,
                message="worker_repeated_failures",
                metadata=metadata,
            )
        return ReadinessCheck(
            status=CHECK_OK,
            required=True,
            metadata=metadata,
        )


def _age_seconds(timestamp: str) -> float:
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds())


def _failed_probe(
    message: str,
    *,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> ReadinessCheck:
    return ReadinessCheck(
        status=CHECK_UNAVAILABLE,
        required=True,
        message=message,
        metadata=metadata or {},
    )
