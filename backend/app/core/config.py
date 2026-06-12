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
    auth_admin_email: str = "969348539@qq.com"
    auth_admin_password: str = "Intertek_AI"
    auth_session_ttl_hours: int = 24 * 14
    auth_password_reset_ttl_minutes: int = 30
    auth_password_hash_iterations: int = 260_000

    @property
    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def workspace_root(self) -> Path:
        return self.backend_root.parent

    @property
    def storage_root(self) -> Path:
        if self.excel_storage_root.strip():
            return Path(self.excel_storage_root).expanduser().resolve()
        return (self.workspace_root / "storage").resolve()

    @property
    def database_path(self) -> Path:
        if self.excel_database_path.strip():
            return Path(self.excel_database_path).expanduser().resolve()
        return (self.storage_root / "excel-workspace.sqlite3").resolve()

    @property
    def cors_origins(self) -> list[str]:
        return self._split_csv(self.app_cors_origins)

    @property
    def supported_excel_extensions(self) -> tuple[str, ...]:
        return tuple(item.lower() for item in self._split_csv(self.excel_supported_extensions))

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
