from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.dialogue import LangGraphChatWorkflow
from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.llm.siliconflow_client import (
    LlmProviderConfig,
    MultiProviderLlmClient,
    SiliconFlowConfig,
)
from app.adapters.pdf.factory import (
    create_pdf_parser,
    create_pdf_parser_profiles,
    get_default_pdf_parser_profile_id,
    get_pdf_parser_profiles,
    get_pdf_parser_status,
)
from app.adapters.repositories.sqlite.policies import (
    SQLiteConnectionPolicy,
    SQLiteMaintenancePolicy,
)
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.retrieval.http_models import (
    HttpPdfRerankerGateway,
    OpenAiCompatiblePdfEmbeddingGateway,
)
from app.adapters.retrieval.qdrant_store import QdrantPdfVectorStore
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.application.auth.rate_limit import AuthenticationRateLimiter
from app.application.auth.service import AuthService
from app.application.chat.cancellation import ChatCancellationRegistry
from app.application.chat.policy import ChatServicePolicy
from app.application.chat.service import ChatService
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.application.excel_assets.upload_tasks import UploadTaskService, UploadTaskWorker
from app.application.llm_preferences import WorkspaceLlmPreferenceService
from app.application.operational.readiness import ReadinessService, WorkerReadinessProbe
from app.application.pdf_knowledge import (
    PdfChatService,
    PdfDocumentRankingService,
    PdfKnowledgeService,
    PdfSummaryTaskWorker,
    PdfUploadTaskWorker,
    PdfVectorIndexingService,
    PdfVectorIndexTaskWorker,
)
from app.application.pdf_knowledge.chat_policy import PdfChatPolicy
from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.llm_catalog import (
    DEEPSEEK_PROVIDER,
    SILICONFLOW_PROVIDER,
    VOLCENGINE_ARK_PROVIDER,
    llm_provider_label,
)
from app.domain.models import AuthenticatedUser, UserRole
from app.ports.chat_workflow import ChatWorkflow
from app.ports.llm_client import LlmClient

auth_scheme = HTTPBearer(auto_error=False)
AuthCredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(auth_scheme),
]
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


@lru_cache(maxsize=1)
def get_excel_repository() -> SQLiteExcelAssetRepository:
    settings = get_settings()
    repository = SQLiteExcelAssetRepository(
        settings.database_path,
        connection_policy=SQLiteConnectionPolicy(
            maintenance_interval_seconds=settings.maintenance_interval_seconds,
        ),
        maintenance_policy=SQLiteMaintenancePolicy(
            auth_session_retention_days=settings.maintenance_auth_session_retention_days,
            password_reset_token_retention_days=(
                settings.maintenance_password_reset_token_retention_days
            ),
        ),
    )
    repository.initialize()
    return repository


@lru_cache(maxsize=1)
def get_excel_asset_service() -> ExcelAssetService:
    settings = get_settings()
    return ExcelAssetService(
        repository=get_excel_repository(),
        storage=FilesystemExcelArtifactStorage(settings.storage_root),
        workbook_reader=OpenpyxlWorkbookReader(),
    )


@lru_cache(maxsize=1)
def get_upload_task_service() -> UploadTaskService:
    settings = get_settings()
    return UploadTaskService(
        repository=get_excel_repository(),
        storage_root=settings.storage_root,
    )


@lru_cache(maxsize=1)
def get_upload_task_worker() -> UploadTaskWorker:
    settings = get_settings()
    return UploadTaskWorker(
        repository=get_excel_repository(),
        excel_assets=get_excel_asset_service(),
        storage_root=settings.storage_root,
        poll_interval_seconds=settings.upload_task_worker_poll_interval_seconds,
        lease_seconds=settings.upload_task_stale_processing_minutes * 60,
    )


@lru_cache(maxsize=1)
def get_pdf_knowledge_service() -> PdfKnowledgeService:
    settings = get_settings()
    parser_profiles = get_pdf_parser_profiles(settings)
    return PdfKnowledgeService(
        repository=get_excel_repository(),
        storage_root=settings.storage_root,
        parser=create_pdf_parser(settings),
        parser_status=get_pdf_parser_status(settings),
        parser_profiles=create_pdf_parser_profiles(settings),
        parser_profile_statuses={
            profile.profile_id: profile.status
            for profile in parser_profiles
        },
        parser_profile_descriptors=parser_profiles,
        default_parser_profile_id=get_default_pdf_parser_profile_id(settings),
        llm_client=get_llm_client(),
        llm_preferences=get_llm_preference_service(),
        vector_embedding_revision=(
            settings.pdf_embedding_revision
            if settings.pdf_vector_indexing_active
            else None
        ),
        vector_embedding_dimension=settings.pdf_embedding_dimension,
        pdf_chunk_max_characters=settings.pdf_document_chunk_max_characters,
    )


@lru_cache(maxsize=1)
def get_pdf_upload_task_worker() -> PdfUploadTaskWorker:
    settings = get_settings()
    return PdfUploadTaskWorker(
        repository=get_excel_repository(),
        pdf_knowledge=get_pdf_knowledge_service(),
        storage_root=settings.storage_root,
        poll_interval_seconds=settings.pdf_upload_task_worker_poll_interval_seconds,
        lease_seconds=max(
            settings.pdf_upload_task_stale_processing_minutes * 60,
            settings.mineru_timeout_seconds + 60,
            settings.mineru_cloud_timeout_seconds + 60,
        ),
    )


@lru_cache(maxsize=1)
def get_pdf_summary_task_worker() -> PdfSummaryTaskWorker:
    settings = get_settings()
    return PdfSummaryTaskWorker(
        repository=get_excel_repository(),
        pdf_knowledge=get_pdf_knowledge_service(),
        poll_interval_seconds=settings.pdf_summary_task_worker_poll_interval_seconds,
    )


@lru_cache(maxsize=1)
def get_pdf_embedding_gateway() -> OpenAiCompatiblePdfEmbeddingGateway:
    settings = get_settings()
    return OpenAiCompatiblePdfEmbeddingGateway(
        api_base_url=settings.pdf_embedding_resolved_api_base_url,
        api_key=settings.pdf_embedding_resolved_api_key,
        model=settings.pdf_embedding_model,
        revision=settings.pdf_embedding_revision,
        embedding_dimension=settings.pdf_embedding_dimension,
        max_input_characters=settings.pdf_document_chunk_max_characters,
        timeout_seconds=settings.pdf_embedding_timeout_seconds,
        batch_size=settings.pdf_embedding_batch_size,
    )


@lru_cache(maxsize=1)
def get_pdf_vector_store() -> QdrantPdfVectorStore:
    settings = get_settings()
    return QdrantPdfVectorStore(
        api_base_url=settings.pdf_qdrant_api_base_url,
        api_key=settings.pdf_qdrant_api_key,
        collection_name=settings.pdf_qdrant_collection,
        embedding_dimension=settings.pdf_embedding_dimension,
        timeout_seconds=settings.pdf_qdrant_timeout_seconds,
        auto_bootstrap=settings.pdf_qdrant_auto_bootstrap_active,
    )


@lru_cache(maxsize=1)
def get_pdf_reranker_gateway() -> HttpPdfRerankerGateway:
    settings = get_settings()
    return HttpPdfRerankerGateway(
        api_base_url=settings.pdf_reranker_resolved_api_base_url,
        api_key=settings.pdf_reranker_resolved_api_key,
        model=settings.pdf_reranker_model,
        revision=settings.pdf_reranker_revision,
        timeout_seconds=settings.pdf_reranker_timeout_seconds,
        batch_size=settings.pdf_reranker_batch_size,
        max_batch_characters=settings.pdf_reranker_max_batch_characters,
    )


@lru_cache(maxsize=1)
def get_pdf_document_ranking_service() -> PdfDocumentRankingService:
    settings = get_settings()
    return PdfDocumentRankingService(
        repository=get_excel_repository(),
        embedding=get_pdf_embedding_gateway(),
        vector_store=get_pdf_vector_store(),
        reranker=get_pdf_reranker_gateway(),
        rerank_max_document_characters=(
            settings.pdf_reranker_max_document_characters
        ),
    )


@lru_cache(maxsize=1)
def get_pdf_vector_index_task_worker() -> PdfVectorIndexTaskWorker:
    settings = get_settings()
    return PdfVectorIndexTaskWorker(
        repository=get_excel_repository(),
        indexing=PdfVectorIndexingService(
            repository=get_excel_repository(),
            embedding=get_pdf_embedding_gateway(),
            vector_store=get_pdf_vector_store(),
        ),
        poll_interval_seconds=settings.pdf_vector_worker_poll_interval_seconds,
        lease_seconds=settings.pdf_vector_worker_lease_seconds,
        max_attempts=settings.pdf_vector_worker_max_attempts,
        retry_max_seconds=settings.pdf_vector_worker_retry_max_seconds,
        reconciliation_embedding_revision=settings.pdf_embedding_revision,
        reconciliation_embedding_dimension=settings.pdf_embedding_dimension,
        reconciliation_interval_seconds=(
            settings.pdf_vector_reconciliation_interval_seconds
        ),
        reconciliation_batch_size=settings.pdf_vector_reconciliation_batch_size,
    )


def get_readiness_service(
    repository: Annotated[
        SQLiteExcelAssetRepository,
        Depends(get_excel_repository),
    ],
) -> ReadinessService:
    settings = get_settings()
    return ReadinessService(
        settings=settings,
        sqlite_inspector=repository.inspect_runtime,
        mineru_inspector=lambda: get_pdf_parser_status(settings),
        workers={
            "excel_upload_worker": WorkerReadinessProbe(
                enabled=settings.upload_task_worker_enabled,
                status_provider=get_upload_task_worker().runtime_status,
                idle_stale_seconds=max(
                    5.0,
                    settings.upload_task_worker_poll_interval_seconds * 10,
                ),
                busy_stale_seconds=max(
                    60.0,
                    settings.upload_task_stale_processing_minutes * 60,
                ),
            ),
            "pdf_upload_worker": WorkerReadinessProbe(
                enabled=settings.pdf_upload_task_worker_enabled,
                status_provider=get_pdf_upload_task_worker().runtime_status,
                idle_stale_seconds=max(
                    5.0,
                    settings.pdf_upload_task_worker_poll_interval_seconds * 10,
                ),
                busy_stale_seconds=max(
                    settings.pdf_upload_task_stale_processing_minutes * 60,
                    settings.mineru_timeout_seconds + 60,
                    settings.mineru_cloud_timeout_seconds + 60,
                ),
            ),
            "pdf_summary_worker": WorkerReadinessProbe(
                enabled=settings.pdf_summary_task_worker_enabled,
                status_provider=get_pdf_summary_task_worker().runtime_status,
                idle_stale_seconds=max(
                    5.0,
                    settings.pdf_summary_task_worker_poll_interval_seconds * 10,
                ),
                busy_stale_seconds=max(
                    60.0,
                    settings.pdf_summary_task_stale_running_minutes * 60,
                ),
            ),
            **(
                {
                    "pdf_vector_worker": WorkerReadinessProbe(
                        enabled=True,
                        status_provider=get_pdf_vector_index_task_worker().runtime_status,
                        idle_stale_seconds=max(
                            5.0,
                            settings.pdf_vector_worker_poll_interval_seconds * 10,
                        ),
                        busy_stale_seconds=max(
                            60.0,
                            settings.pdf_vector_worker_lease_seconds,
                        ),
                    )
                }
                if settings.pdf_vector_indexing_active
                else {}
            ),
        },
        vector_queue_inspector=(
            repository.inspect_pdf_vector_queue
            if settings.pdf_vector_indexing_active
            else None
        ),
        vector_store_inspector=(
            get_pdf_vector_store().inspect_runtime
            if settings.pdf_vector_indexing_active
            else None
        ),
    )


@lru_cache(maxsize=1)
def get_pdf_chat_service() -> PdfChatService:
    settings = get_settings()
    return PdfChatService(
        llm_client=get_llm_client(),
        sessions=get_excel_repository(),
        document_ranking=(
            get_pdf_document_ranking_service()
            if settings.pdf_vector_ranking_active
            else None
        ),
        policy=PdfChatPolicy(
            max_routed_documents=4,
            full_document_context=True,
            max_answer_context_chunks=settings.pdf_answer_max_context_chunks,
            max_answer_context_characters=(
                settings.pdf_answer_max_context_characters
            ),
            max_answer_context_tokens=settings.pdf_answer_max_context_tokens,
        ),
    )


@lru_cache(maxsize=1)
def get_document_summary_service() -> DocumentSummaryService:
    return DocumentSummaryService(
        excel_assets=get_excel_asset_service(),
        llm_client=get_llm_client(),
        repository=get_excel_repository(),
        llm_preferences=get_llm_preference_service(),
    )


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    settings = get_settings()
    return ChatService(
        excel_assets=get_excel_asset_service(),
        summaries=get_document_summary_service(),
        llm_client=get_llm_client(),
        sessions=get_excel_repository(),
        llm_preferences=get_llm_preference_service(),
        policy=ChatServicePolicy(max_answer_rows=settings.llm_answer_max_rows),
        workflow=get_chat_workflow(),
    )


@lru_cache(maxsize=1)
def get_llm_preference_service() -> WorkspaceLlmPreferenceService:
    return WorkspaceLlmPreferenceService(
        repository=get_excel_repository(),
        settings=get_settings(),
    )


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    settings = get_settings()
    service = AuthService(
        repository=get_excel_repository(),
        admin_email=settings.auth_admin_email,
        admin_password=settings.auth_admin_password,
        session_ttl_hours=settings.auth_session_ttl_hours,
        password_reset_ttl_minutes=settings.auth_password_reset_ttl_minutes,
        password_hash_iterations=settings.auth_password_hash_iterations,
        expose_reset_token=settings.auth_expose_reset_token,
        login_rate_limiter=AuthenticationRateLimiter(
            max_failed_attempts=settings.auth_login_rate_limit_max_failures,
            window_seconds=settings.auth_login_rate_limit_window_seconds,
            repository=get_excel_repository(),
        ),
    )
    service.initialize()
    return service


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    request: Request,
    credentials: AuthCredentialsDependency,
    service: AuthServiceDependency,
) -> AuthenticatedUser:
    token: str | None = None
    authenticated_with_cookie = False
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    else:
        settings = get_settings()
        token = request.cookies.get(settings.auth_cookie_name)
        authenticated_with_cookie = token is not None
        if authenticated_with_cookie and request.method.upper() not in SAFE_HTTP_METHODS:
            csrf_cookie = request.cookies.get(settings.auth_csrf_cookie_name)
            csrf_header = request.headers.get("x-csrf-token")
            if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                raise AuthenticationError("csrf token is invalid or missing")
    if token is None:
        raise AuthenticationError("authentication is required")
    return service.get_user_for_token(token)


CurrentUserDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_admin_user(
    user: CurrentUserDependency,
) -> AuthenticatedUser:
    if user.role != UserRole.ADMIN:
        raise AuthorizationError("administrator access is required")
    return user


@lru_cache(maxsize=1)
def get_chat_workflow() -> ChatWorkflow:
    return LangGraphChatWorkflow()


@lru_cache(maxsize=1)
def get_chat_cancellation_registry() -> ChatCancellationRegistry:
    settings = get_settings()
    return ChatCancellationRegistry(
        pending_retention_seconds=settings.chat_cancellation_retention_seconds,
        repository=get_excel_repository(),
    )


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    settings = get_settings()
    if settings.llm_provider.lower() == "fake":
        return FakeLlmClient()
    return MultiProviderLlmClient(
        SiliconFlowConfig(
            api_base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            summary_model=settings.llm_summary_model,
            router_model=settings.llm_router_model,
            answer_model=settings.llm_answer_model,
            timeout_seconds=settings.llm_request_timeout_seconds,
            summary_max_profile_rows=settings.llm_summary_max_profile_rows,
        ),
        extra_providers=_configured_llm_providers(settings),
        default_providers={
            "summary": settings.llm_summary_provider or SILICONFLOW_PROVIDER,
            "router": settings.llm_router_provider or SILICONFLOW_PROVIDER,
            "answer": settings.llm_answer_provider or SILICONFLOW_PROVIDER,
        },
    )


def _configured_llm_providers(settings: Settings) -> dict[str, LlmProviderConfig]:
    return {
        DEEPSEEK_PROVIDER: _llm_provider_config(
            provider=DEEPSEEK_PROVIDER,
            api_base_url=settings.deepseek_api_base_url,
            api_key=settings.deepseek_api_key,
            summary_model=settings.deepseek_summary_model,
            router_model=settings.deepseek_router_model,
            answer_model=settings.deepseek_answer_model,
        ),
        VOLCENGINE_ARK_PROVIDER: _llm_provider_config(
            provider=VOLCENGINE_ARK_PROVIDER,
            api_base_url=settings.volcengine_ark_api_base_url,
            api_key=settings.volcengine_ark_api_key,
            summary_model=settings.volcengine_ark_summary_model,
            router_model=settings.volcengine_ark_router_model,
            answer_model=settings.volcengine_ark_answer_model,
        ),
    }


def _llm_provider_config(
    *,
    provider: str,
    api_base_url: str,
    api_key: str,
    summary_model: str,
    router_model: str,
    answer_model: str,
) -> LlmProviderConfig:
    return LlmProviderConfig(
        provider=provider,
        label=llm_provider_label(provider),
        api_base_url=api_base_url,
        api_key=api_key,
        summary_model=summary_model,
        router_model=router_model,
        answer_model=answer_model,
    )
