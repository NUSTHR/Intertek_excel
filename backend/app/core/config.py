from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.llm_catalog import (
    DEFAULT_ANSWER_MODEL,
    DEFAULT_ANSWER_PROVIDER,
    DEFAULT_DEEPSEEK_ANSWER_MODEL,
    DEFAULT_DEEPSEEK_ROUTER_MODEL,
    DEFAULT_DEEPSEEK_SUMMARY_MODEL,
    DEFAULT_ROUTER_MODEL,
    DEFAULT_ROUTER_PROVIDER,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_SUMMARY_PROVIDER,
    DEFAULT_VOLCENGINE_ARK_ANSWER_MODEL,
    DEFAULT_VOLCENGINE_ARK_ROUTER_MODEL,
    DEFAULT_VOLCENGINE_ARK_SUMMARY_MODEL,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "excel-workspace-backend"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8090
    app_cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    excel_database_path: str = ""
    excel_storage_root: str = ""
    excel_supported_extensions: str = ".xls,.xlsx,.xlsm,.xltx,.xltm"
    excel_preview_max_rows: int = 500
    excel_max_upload_bytes: int = 50 * 1024 * 1024
    llm_provider: str = "siliconflow"
    llm_api_base_url: str = "https://api.siliconflow.cn/v1"
    llm_api_key: str = ""
    llm_summary_provider: str = DEFAULT_SUMMARY_PROVIDER
    llm_summary_model: str = DEFAULT_SUMMARY_MODEL
    llm_router_provider: str = DEFAULT_ROUTER_PROVIDER
    llm_router_model: str = DEFAULT_ROUTER_MODEL
    llm_answer_provider: str = DEFAULT_ANSWER_PROVIDER
    llm_answer_model: str = DEFAULT_ANSWER_MODEL
    deepseek_api_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_summary_model: str = DEFAULT_DEEPSEEK_SUMMARY_MODEL
    deepseek_router_model: str = DEFAULT_DEEPSEEK_ROUTER_MODEL
    deepseek_answer_model: str = DEFAULT_DEEPSEEK_ANSWER_MODEL
    volcengine_ark_api_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_ark_api_key: str = ""
    volcengine_ark_summary_model: str = DEFAULT_VOLCENGINE_ARK_SUMMARY_MODEL
    volcengine_ark_router_model: str = DEFAULT_VOLCENGINE_ARK_ROUTER_MODEL
    volcengine_ark_answer_model: str = DEFAULT_VOLCENGINE_ARK_ANSWER_MODEL
    llm_request_timeout_seconds: float = 60.0
    llm_summary_max_profile_rows: int = 10
    llm_answer_max_rows: int = 20_000
    maintenance_interval_seconds: float = 300.0
    maintenance_auth_session_retention_days: int = 30
    maintenance_password_reset_token_retention_days: int = 7
    upload_task_worker_enabled: bool = True
    upload_task_worker_poll_interval_seconds: float = 0.5
    upload_task_stale_processing_minutes: int = 60
    pdf_upload_task_worker_enabled: bool = True
    pdf_upload_task_worker_poll_interval_seconds: float = 0.5
    pdf_upload_task_stale_processing_minutes: int = 60
    pdf_summary_task_worker_enabled: bool = True
    pdf_summary_task_worker_poll_interval_seconds: float = 0.5
    pdf_summary_task_stale_running_minutes: int = 60
    pdf_parser_backend: str = "fake"
    mineru_command: str = "mineru"
    mineru_timeout_seconds: float = 300.0
    mineru_cli_backend: str = "pipeline"
    mineru_extra_args: str = ""
    mineru_cloud_api_base_url: str = "https://mineru.net/api/v4"
    mineru_cloud_api_token: str = ""
    mineru_cloud_access_key: str = ""
    mineru_cloud_secret_key: str = ""
    mineru_cloud_model_version: str = "vlm"
    mineru_cloud_timeout_seconds: float = 1200.0
    mineru_cloud_poll_interval_seconds: float = 5.0
    mineru_cloud_language: str = "ch"
    mineru_cloud_enable_formula: bool = True
    mineru_cloud_enable_table: bool = True
    mineru_cloud_is_ocr: bool = False
    chat_cancellation_retention_seconds: int = 300
    auth_admin_email: str = "admin@qq.com"
    auth_admin_password: str = "admin"
    auth_session_ttl_hours: int = 24 * 14
    auth_password_reset_ttl_minutes: int = 30
    auth_password_hash_iterations: int = 260_000
    auth_expose_reset_token: bool = True
    auth_login_rate_limit_max_failures: int = 5
    auth_login_rate_limit_window_seconds: int = 300
    auth_cookie_name: str = "excelai_session"
    auth_csrf_cookie_name: str = "excelai_csrf"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    log_level: str = "INFO"
    log_file_path: str = ""
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def workspace_root(self) -> Path:
        return self.backend_root.parent

    @property
    def storage_root(self) -> Path:
        if self.excel_storage_root.strip():
            return self._runtime_path(self.excel_storage_root)
        return (self.workspace_root / "storage").resolve()

    @property
    def database_path(self) -> Path:
        if self.excel_database_path.strip():
            return self._runtime_path(self.excel_database_path)
        return (self.storage_root / "excel-workspace.sqlite3").resolve()

    @property
    def log_path(self) -> Path:
        if self.log_file_path.strip():
            return self._runtime_path(self.log_file_path)
        return (self.storage_root / "logs" / "backend.log").resolve()

    def _runtime_path(self, configured_path: str) -> Path:
        path = Path(configured_path.strip()).expanduser()
        if path.is_absolute():
            return path.resolve()
        resolved_path = (self.workspace_root / path).resolve()
        if not resolved_path.is_relative_to(self.workspace_root):
            raise ValueError("relative runtime path must stay within project root")
        return resolved_path

    @property
    def cors_origins(self) -> list[str]:
        return self._split_csv(self.app_cors_origins)

    @property
    def supported_excel_extensions(self) -> tuple[str, ...]:
        return tuple(item.lower() for item in self._split_csv(self.excel_supported_extensions))

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}

    def validate_runtime_safety(self) -> None:
        if not self.is_production:
            return

        errors: list[str] = []
        if self.auth_admin_password == "admin":
            errors.append("AUTH_ADMIN_PASSWORD must be changed for production")
        if self.auth_expose_reset_token:
            errors.append("AUTH_EXPOSE_RESET_TOKEN must be false for production")
        if not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true for production")
        if self.auth_cookie_samesite.strip().lower() not in {"lax", "strict", "none"}:
            errors.append("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        if self.auth_cookie_samesite.strip().lower() == "none" and not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true when AUTH_COOKIE_SAMESITE=none")
        if self.auth_login_rate_limit_max_failures <= 0:
            errors.append("AUTH_LOGIN_RATE_LIMIT_MAX_FAILURES must be greater than 0")
        if self.auth_login_rate_limit_window_seconds <= 0:
            errors.append("AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS must be greater than 0")
        if self.log_max_bytes <= 0:
            errors.append("LOG_MAX_BYTES must be greater than 0")
        if self.log_backup_count < 1:
            errors.append("LOG_BACKUP_COUNT must be at least 1")
        if not self.cors_origins:
            errors.append("APP_CORS_ORIGINS must be set for production")
        for origin in self.cors_origins:
            normalized_origin = origin.lower()
            if origin == "*":
                errors.append("APP_CORS_ORIGINS must not contain '*' in production")
            if "localhost" in normalized_origin or "127.0.0.1" in normalized_origin:
                errors.append(
                    "APP_CORS_ORIGINS must not contain localhost origins in production"
                )
                break
        if self.llm_provider.strip().lower() == "fake":
            errors.append("LLM_PROVIDER=fake is not allowed in production")

        provider_keys = {
            "siliconflow": self.llm_api_key,
            "deepseek": self.deepseek_api_key,
            "volcengine_ark": self.volcengine_ark_api_key,
        }
        for stage, provider in {
            "summary": self.llm_summary_provider,
            "router": self.llm_router_provider,
            "answer": self.llm_answer_provider,
        }.items():
            provider_key = provider_keys.get(provider.strip().lower())
            if provider_key is not None and not provider_key.strip():
                errors.append(f"{stage} provider '{provider}' requires an API key in production")

        if errors:
            details = "; ".join(errors)
            raise RuntimeError(f"unsafe production configuration: {details}")

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
