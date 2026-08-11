from dataclasses import dataclass

SQLITE_CONNECTION_TIMEOUT_SECONDS = 30.0
SQLITE_BUSY_TIMEOUT_MS = 30000
SQLITE_WAL_AUTOCHECKPOINT_PAGES = 1000
SQLITE_MAINTENANCE_INTERVAL_SECONDS = 300.0
AUTH_SESSION_RETENTION_DAYS = 30
PASSWORD_RESET_TOKEN_RETENTION_DAYS = 7
LOGIN_ATTEMPT_RETENTION_DAYS = 1
PDF_SUMMARY_TASK_RETENTION_DAYS = 90
PDF_CLEANUP_JOB_RETENTION_DAYS = 30


@dataclass(frozen=True)
class SQLiteConnectionPolicy:
    timeout_seconds: float = SQLITE_CONNECTION_TIMEOUT_SECONDS
    busy_timeout_ms: int = SQLITE_BUSY_TIMEOUT_MS
    wal_autocheckpoint_pages: int = SQLITE_WAL_AUTOCHECKPOINT_PAGES
    maintenance_interval_seconds: float = SQLITE_MAINTENANCE_INTERVAL_SECONDS


@dataclass(frozen=True)
class SQLiteMaintenancePolicy:
    auth_session_retention_days: int = AUTH_SESSION_RETENTION_DAYS
    password_reset_token_retention_days: int = PASSWORD_RESET_TOKEN_RETENTION_DAYS
    login_attempt_retention_days: int = LOGIN_ATTEMPT_RETENTION_DAYS
    pdf_summary_task_retention_days: int = PDF_SUMMARY_TASK_RETENTION_DAYS
    pdf_cleanup_job_retention_days: int = PDF_CLEANUP_JOB_RETENTION_DAYS
