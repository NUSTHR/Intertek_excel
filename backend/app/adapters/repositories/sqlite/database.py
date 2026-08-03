import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from threading import Lock

from app.adapters.repositories.sqlite.maintenance import SQLiteOperationalMaintenance
from app.adapters.repositories.sqlite.policies import (
    SQLiteConnectionPolicy,
    SQLiteMaintenancePolicy,
)
from app.core.time import utc_now_iso


class SQLiteDatabase:
    """Shared connection, PRAGMA, and operational-maintenance owner."""

    def __init__(
        self,
        database_path: Path,
        *,
        connection_policy: SQLiteConnectionPolicy,
        maintenance_policy: SQLiteMaintenancePolicy,
    ) -> None:
        self.path = database_path
        self.connection_policy = connection_policy
        self._maintenance = SQLiteOperationalMaintenance(maintenance_policy)
        self._last_maintenance_at = 0.0
        self._maintenance_lock = Lock()

    def connect(
        self,
        *,
        run_maintenance: bool = True,
        maintenance_runner: Callable[[sqlite3.Connection], object] | None = None,
    ) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.connection_policy.timeout_seconds,
            isolation_level="IMMEDIATE",
        )
        connection.row_factory = sqlite3.Row
        self._configure_connection(connection)
        if run_maintenance:
            self._maybe_run_connection_maintenance(
                connection,
                maintenance_runner=maintenance_runner,
            )
        return connection

    def run_operational_maintenance(self, now_iso: str | None = None) -> dict[str, int]:
        with self.connect(run_maintenance=False) as connection:
            result = self._run_connection_maintenance(connection, now_iso=now_iso)
            self._last_maintenance_at = time.monotonic()
        return result

    def _configure_connection(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            f"PRAGMA busy_timeout = {self.connection_policy.busy_timeout_ms}"
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            "PRAGMA wal_autocheckpoint = "
            f"{self.connection_policy.wal_autocheckpoint_pages}"
        )

    def _maybe_run_connection_maintenance(
        self,
        connection: sqlite3.Connection,
        *,
        maintenance_runner: Callable[[sqlite3.Connection], object] | None = None,
    ) -> None:
        now = time.monotonic()
        if (
            self.connection_policy.maintenance_interval_seconds > 0
            and now - self._last_maintenance_at
            < self.connection_policy.maintenance_interval_seconds
        ):
            return
        if not self._maintenance_lock.acquire(blocking=False):
            return
        try:
            now = time.monotonic()
            if (
                self.connection_policy.maintenance_interval_seconds > 0
                and now - self._last_maintenance_at
                < self.connection_policy.maintenance_interval_seconds
            ):
                return
            runner = maintenance_runner or self._run_connection_maintenance
            runner(connection)
            self._last_maintenance_at = now
        finally:
            self._maintenance_lock.release()

    def _run_connection_maintenance(
        self,
        connection: sqlite3.Connection,
        *,
        now_iso: str | None = None,
    ) -> dict[str, int]:
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        return self._maintenance.cleanup_expired_operational_records(
            connection,
            now_iso=now_iso or utc_now_iso(),
        )
