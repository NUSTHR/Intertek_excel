from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

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
    excel_archive_retention_days: int = 30
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
    llm_request_timeout_seconds: float = 120.0
    llm_summary_max_profile_rows: int = 10
    llm_answer_max_rows: int = 20_000
    pdf_routing_max_request_characters: int = 120_000
    pdf_routing_max_batch_documents: int = 20
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
    # Deprecated compatibility switch. New deployments must use the independent
    # indexing/ranking switches so projections can be backfilled before serving.
    pdf_vector_search_enabled: bool | None = None
    pdf_vector_indexing_enabled: bool | None = None
    pdf_vector_ranking_enabled: bool | None = None
    pdf_vector_worker_poll_interval_seconds: float = 1.0
    pdf_vector_worker_lease_seconds: float = 900.0
    pdf_vector_worker_max_attempts: int = 20
    pdf_vector_worker_retry_max_seconds: int = 900
    pdf_vector_reconciliation_interval_seconds: float = 60.0
    pdf_vector_reconciliation_batch_size: int = 100
    pdf_answer_max_context_chunks: int = 160
    pdf_answer_max_context_characters: int = 120_000
    pdf_answer_max_context_tokens: int = 30_000
    pdf_embedding_api_base_url: str = ""
    pdf_embedding_api_key: str = ""
    pdf_embedding_model: str = "Qwen/Qwen3-Embedding-8B"
    pdf_embedding_revision: str = (
        "siliconflow-qwen3-embedding-8b-d4096-query-v1-doc-v1"
    )
    pdf_embedding_dimension: int = 4096
    pdf_embedding_batch_size: int = 16
    pdf_document_chunk_max_characters: int = 12_000
    pdf_embedding_timeout_seconds: float = 120.0
    pdf_reranker_api_base_url: str = ""
    pdf_reranker_api_key: str = ""
    pdf_reranker_model: str = "Qwen/Qwen3-Reranker-8B"
    pdf_reranker_revision: str = "siliconflow-qwen3-reranker-8b-v1"
    pdf_reranker_timeout_seconds: float = 120.0
    pdf_reranker_batch_size: int = 16
    pdf_reranker_max_document_characters: int = 24_000
    pdf_reranker_max_batch_characters: int = 120_000
    pdf_qdrant_api_base_url: str = "http://127.0.0.1:6333"
    pdf_qdrant_api_key: str = ""
    pdf_qdrant_collection: str = "pdf_chunks_qwen3_4096_v1"
    pdf_qdrant_timeout_seconds: float = 30.0
    pdf_qdrant_auto_bootstrap: bool | None = None
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
    readiness_disk_warning_free_bytes: int = 2 * 1024 * 1024 * 1024
    readiness_disk_critical_free_bytes: int = 512 * 1024 * 1024
    readiness_disk_warning_free_percent: float = 10.0
    readiness_disk_critical_free_percent: float = 3.0

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

    @property
    def pdf_vector_indexing_active(self) -> bool:
        if self.pdf_vector_indexing_enabled is not None:
            return self.pdf_vector_indexing_enabled
        return bool(self.pdf_vector_search_enabled)

    @property
    def pdf_vector_ranking_active(self) -> bool:
        if self.pdf_vector_ranking_enabled is not None:
            return self.pdf_vector_ranking_enabled
        return bool(self.pdf_vector_search_enabled)

    @property
    def pdf_embedding_resolved_api_base_url(self) -> str:
        return self.pdf_embedding_api_base_url.strip() or self.llm_api_base_url.strip()

    @property
    def pdf_embedding_resolved_api_key(self) -> str:
        return self.pdf_embedding_api_key.strip() or self.llm_api_key.strip()

    @property
    def pdf_reranker_resolved_api_base_url(self) -> str:
        return self.pdf_reranker_api_base_url.strip() or self.llm_api_base_url.strip()

    @property
    def pdf_reranker_resolved_api_key(self) -> str:
        return self.pdf_reranker_api_key.strip() or self.llm_api_key.strip()

    @property
    def pdf_qdrant_auto_bootstrap_active(self) -> bool:
        if self.pdf_qdrant_auto_bootstrap is not None:
            return self.pdf_qdrant_auto_bootstrap
        return not self.is_production

    def validate_runtime_safety(self) -> None:
        routing_limits = {
            "PDF_ROUTING_MAX_REQUEST_CHARACTERS": (
                self.pdf_routing_max_request_characters
            ),
            "PDF_ROUTING_MAX_BATCH_DOCUMENTS": self.pdf_routing_max_batch_documents,
        }
        invalid_routing_limits = [
            name for name, value in routing_limits.items() if value < 1
        ]
        if invalid_routing_limits:
            raise RuntimeError(
                "invalid PDF routing configuration: "
                + "; ".join(
                    f"{name} must be positive" for name in invalid_routing_limits
                )
            )
        if self.pdf_routing_max_request_characters <= 9_000:
            raise RuntimeError(
                "invalid PDF routing configuration: "
                "PDF_ROUTING_MAX_REQUEST_CHARACTERS must be greater than 9000"
            )
        if self.pdf_routing_max_batch_documents > 20:
            raise RuntimeError(
                "invalid PDF routing configuration: "
                "PDF_ROUTING_MAX_BATCH_DOCUMENTS must not exceed 20"
            )
        context_limits = {
            "PDF_ANSWER_MAX_CONTEXT_CHUNKS": self.pdf_answer_max_context_chunks,
            "PDF_ANSWER_MAX_CONTEXT_CHARACTERS": (
                self.pdf_answer_max_context_characters
            ),
            "PDF_ANSWER_MAX_CONTEXT_TOKENS": self.pdf_answer_max_context_tokens,
        }
        invalid_context_limits = [
            name for name, value in context_limits.items() if value < 1
        ]
        if invalid_context_limits:
            raise RuntimeError(
                "invalid PDF answer context configuration: "
                + "; ".join(
                    f"{name} must be positive" for name in invalid_context_limits
                )
            )
        if self.pdf_vector_indexing_active or self.pdf_vector_ranking_active:
            vector_errors = self._vector_configuration_errors()
            if vector_errors:
                raise RuntimeError(
                    "invalid PDF vector configuration: "
                    + "; ".join(vector_errors)
                )
        if not self.is_production:
            return

        errors: list[str] = []
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
        if self.readiness_disk_critical_free_bytes < 0:
            errors.append("READINESS_DISK_CRITICAL_FREE_BYTES must not be negative")
        if (
            self.readiness_disk_warning_free_bytes
            < self.readiness_disk_critical_free_bytes
        ):
            errors.append(
                "READINESS_DISK_WARNING_FREE_BYTES must be at least the critical threshold"
            )
        if not 0 <= self.readiness_disk_critical_free_percent <= 100:
            errors.append("READINESS_DISK_CRITICAL_FREE_PERCENT must be between 0 and 100")
        if not (
            self.readiness_disk_critical_free_percent
            <= self.readiness_disk_warning_free_percent
            <= 100
        ):
            errors.append(
                "READINESS_DISK_WARNING_FREE_PERCENT must be between the critical threshold and 100"
            )
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

    def _vector_configuration_errors(self) -> list[str]:
        errors: list[str] = []
        if self.pdf_vector_ranking_active and not self.pdf_vector_indexing_active:
            errors.append(
                "PDF_VECTOR_RANKING_ENABLED requires PDF_VECTOR_INDEXING_ENABLED"
            )
        required_values = {
            "PDF_EMBEDDING_API_BASE_URL": self.pdf_embedding_resolved_api_base_url,
            "PDF_EMBEDDING_MODEL": self.pdf_embedding_model,
            "PDF_EMBEDDING_REVISION": self.pdf_embedding_revision,
            "PDF_QDRANT_API_BASE_URL": self.pdf_qdrant_api_base_url,
            "PDF_QDRANT_COLLECTION": self.pdf_qdrant_collection,
        }
        if self.pdf_vector_ranking_active:
            required_values.update(
                {
                    "PDF_RERANKER_API_BASE_URL": (
                        self.pdf_reranker_resolved_api_base_url
                    ),
                    "PDF_RERANKER_MODEL": self.pdf_reranker_model,
                    "PDF_RERANKER_REVISION": self.pdf_reranker_revision,
                }
            )
        errors.extend(
            f"{name} is required"
            for name, value in required_values.items()
            if not value.strip()
        )
        if self.pdf_embedding_dimension < 1:
            errors.append("PDF_EMBEDDING_DIMENSION must be positive")
        if self.pdf_embedding_batch_size < 1:
            errors.append("PDF_EMBEDDING_BATCH_SIZE must be positive")
        if self.pdf_document_chunk_max_characters < 1:
            errors.append("PDF_DOCUMENT_CHUNK_MAX_CHARACTERS must be positive")
        if self.pdf_reranker_batch_size < 1:
            errors.append("PDF_RERANKER_BATCH_SIZE must be positive")
        if self.pdf_reranker_max_document_characters < 1:
            errors.append("PDF_RERANKER_MAX_DOCUMENT_CHARACTERS must be positive")
        if self.pdf_reranker_max_batch_characters < 1:
            errors.append("PDF_RERANKER_MAX_BATCH_CHARACTERS must be positive")
        if (
            self.pdf_reranker_max_batch_characters
            < self.pdf_reranker_max_document_characters
        ):
            errors.append(
                "PDF_RERANKER_MAX_BATCH_CHARACTERS must be at least "
                "PDF_RERANKER_MAX_DOCUMENT_CHARACTERS"
            )
        for name, timeout_seconds in {
            "PDF_EMBEDDING_TIMEOUT_SECONDS": self.pdf_embedding_timeout_seconds,
            "PDF_RERANKER_TIMEOUT_SECONDS": self.pdf_reranker_timeout_seconds,
            "PDF_QDRANT_TIMEOUT_SECONDS": self.pdf_qdrant_timeout_seconds,
        }.items():
            if timeout_seconds <= 0:
                errors.append(f"{name} must be positive")
        if self.pdf_vector_worker_lease_seconds < 5:
            errors.append("PDF_VECTOR_WORKER_LEASE_SECONDS must be at least 5")
        if self.pdf_vector_worker_max_attempts < 1:
            errors.append("PDF_VECTOR_WORKER_MAX_ATTEMPTS must be positive")
        if self.pdf_vector_worker_retry_max_seconds < 1:
            errors.append("PDF_VECTOR_WORKER_RETRY_MAX_SECONDS must be positive")
        if self.pdf_vector_reconciliation_interval_seconds < 5:
            errors.append(
                "PDF_VECTOR_RECONCILIATION_INTERVAL_SECONDS must be at least 5"
            )
        if self.pdf_vector_reconciliation_batch_size < 1:
            errors.append("PDF_VECTOR_RECONCILIATION_BATCH_SIZE must be positive")
        if self.is_production:
            if not self.pdf_embedding_resolved_api_key:
                errors.append("PDF embedding requires an API key in production")
            if (
                self.pdf_vector_ranking_active
                and not self.pdf_reranker_resolved_api_key
            ):
                errors.append("PDF reranker requires an API key in production")
            if self.pdf_qdrant_auto_bootstrap_active:
                errors.append("PDF_QDRANT_AUTO_BOOTSTRAP must be false in production")
            qdrant_url = urlparse(self.pdf_qdrant_api_base_url.strip())
            qdrant_is_loopback = qdrant_url.hostname in {
                "127.0.0.1",
                "localhost",
                "::1",
            }
            if not qdrant_is_loopback:
                if qdrant_url.scheme != "https":
                    errors.append("remote Qdrant must use HTTPS in production")
                if not self.pdf_qdrant_api_key.strip():
                    errors.append("remote Qdrant requires an API key in production")
        return errors

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
