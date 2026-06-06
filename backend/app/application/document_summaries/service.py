from app.application.excel_assets.service import ExcelAssetService
from app.domain.models import DocumentSummary
from app.ports.llm_client import LlmClient
from app.ports.repository import DocumentSummaryRepository


class DocumentSummaryService:
    def __init__(
        self,
        excel_assets: ExcelAssetService,
        llm_client: LlmClient,
        repository: DocumentSummaryRepository,
    ) -> None:
        self._excel_assets = excel_assets
        self._llm_client = llm_client
        self._repository = repository

    def generate_summary(
        self,
        version_id: str,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> DocumentSummary:
        profile = self._excel_assets.get_profile(version_id)
        summary = self._llm_client.generate_document_summary(
            profile,
            model=model,
            provider=provider,
        )
        self._repository.save_summary(summary)
        return summary

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        return self._repository.get_summary(version_id)

    def list_active_summaries(self) -> list[DocumentSummary]:
        active_version_ids = {
            file.active_version_id
            for file in self._excel_assets.list_files()
            if file.active_version_id is not None
        }
        return [
            summary
            for summary in self._repository.list_summaries()
            if summary.version_id in active_version_ids
        ]
