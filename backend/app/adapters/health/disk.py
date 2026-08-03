import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskRuntimeInspection:
    accessible: bool
    writable: bool
    free_bytes: int
    free_percent: float
    error_code: str | None = None


class DiskRuntimeProbe:
    """Checks the storage filesystem without retaining probe artifacts."""

    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root

    def inspect(self) -> DiskRuntimeInspection:
        if not self._storage_root.is_dir():
            return DiskRuntimeInspection(
                accessible=False,
                writable=False,
                free_bytes=0,
                free_percent=0.0,
                error_code="storage_missing",
            )
        try:
            usage = shutil.disk_usage(self._storage_root)
        except OSError:
            return DiskRuntimeInspection(
                accessible=False,
                writable=False,
                free_bytes=0,
                free_percent=0.0,
                error_code="storage_unavailable",
            )

        writable = False
        probe_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=".readiness-",
                dir=self._storage_root,
            )
            probe_path = Path(raw_path)
            with os.fdopen(descriptor, "wb") as probe:
                probe.write(b"ready")
                probe.flush()
                os.fsync(probe.fileno())
            writable = True
        except OSError:
            writable = False
        finally:
            if probe_path is not None:
                try:
                    probe_path.unlink(missing_ok=True)
                except OSError:
                    writable = False

        free_percent = (
            round((usage.free / usage.total) * 100, 2)
            if usage.total > 0
            else 0.0
        )
        return DiskRuntimeInspection(
            accessible=True,
            writable=writable,
            free_bytes=usage.free,
            free_percent=free_percent,
            error_code=None if writable else "storage_not_writable",
        )
