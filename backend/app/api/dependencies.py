from functools import lru_cache

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.llm.siliconflow_client import SiliconFlowConfig, SiliconFlowLlmClient
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.application.chat.service import ChatService
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.core.config import get_settings
from app.ports.llm_client import LlmClient


@lru_cache(maxsize=1)
def get_excel_repository() -> SQLiteExcelAssetRepository:
    settings = get_settings()
    repository = SQLiteExcelAssetRepository(settings.database_path)
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
def get_document_summary_service() -> DocumentSummaryService:
    return DocumentSummaryService(
        excel_assets=get_excel_asset_service(),
        llm_client=get_llm_client(),
        repository=get_excel_repository(),
    )


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    return ChatService(
        excel_assets=get_excel_asset_service(),
        summaries=get_document_summary_service(),
        llm_client=get_llm_client(),
        sessions=get_excel_repository(),
    )


@lru_cache(maxsize=1)
def get_llm_client() -> LlmClient:
    settings = get_settings()
    if settings.llm_provider.lower() == "fake":
        return FakeLlmClient()
    return SiliconFlowLlmClient(
        SiliconFlowConfig(
            api_base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            router_model=settings.llm_router_model,
            answer_model=settings.llm_answer_model,
            timeout_seconds=settings.llm_request_timeout_seconds,
            summary_max_profile_rows=settings.llm_summary_max_profile_rows,
        )
    )
