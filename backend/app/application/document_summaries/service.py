from app.application.excel_assets.service import ExcelAssetService
from app.core.errors import AssetNotFoundError
from app.domain.models import DocumentSummary, SheetSummary
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
        profile = self._excel_assets.get_summary_profile(version_id)
        summary = self._llm_client.generate_document_summary(
            profile,
            model=model,
            provider=provider,
        )
        self._repository.save_summary(summary)
        return summary

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        return self._repository.get_summary(version_id)

    def update_summary(
        self,
        version_id: str,
        *,
        summary_text: str | None = None,
        business_domain: str | None = None,
        key_topics: list[str] | None = None,
        positive_routing_terms: list[str] | None = None,
        negative_routing_terms: list[str] | None = None,
        exact_identifiers: list[str] | None = None,
        suitable_questions: list[str] | None = None,
        unsuitable_questions: list[str] | None = None,
        sheet_summaries: list[SheetSummary] | None = None,
        routing_notes: str | None = None,
    ) -> DocumentSummary:
        current = self._repository.get_summary(version_id)
        if current is None:
            raise AssetNotFoundError("document summary was not found")

        updated = DocumentSummary(
            summary_id=current.summary_id,
            file_id=current.file_id,
            version_id=current.version_id,
            document_title=current.document_title,
            document_type=current.document_type,
            summary_text=self._clean_text(summary_text, current.summary_text),
            business_domain=self._clean_text(business_domain, current.business_domain),
            coverage_scope=current.coverage_scope,
            key_topics=self._clean_string_list(key_topics, current.key_topics),
            positive_routing_terms=self._clean_string_list(
                positive_routing_terms,
                current.positive_routing_terms,
            ),
            negative_routing_terms=self._clean_string_list(
                negative_routing_terms,
                current.negative_routing_terms,
            ),
            exact_identifiers=self._clean_string_list(
                exact_identifiers,
                current.exact_identifiers,
            ),
            suitable_questions=self._clean_string_list(
                suitable_questions,
                current.suitable_questions,
            ),
            unsuitable_questions=self._clean_string_list(
                unsuitable_questions,
                current.unsuitable_questions,
            ),
            sheet_summaries=(
                sheet_summaries
                if sheet_summaries is not None
                else current.sheet_summaries
            ),
            routing_notes=self._clean_optional_text(routing_notes, current.routing_notes),
            created_at=current.created_at,
        )
        self._repository.save_summary(updated)
        return updated

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

    def _clean_text(self, value: str | None, fallback: str) -> str:
        if value is None:
            return fallback
        normalized = value.strip()
        return normalized or fallback

    def _clean_optional_text(self, value: str | None, fallback: str) -> str:
        if value is None:
            return fallback
        return value.strip()

    def _clean_string_list(
        self,
        values: list[str] | None,
        fallback: list[str],
    ) -> list[str]:
        if values is None:
            return fallback
        seen: set[str] = set()
        cleaned: list[str] = []
        for value in values:
            normalized = value.strip()
            key = normalized.casefold()
            if normalized and key not in seen:
                cleaned.append(normalized)
                seen.add(key)
        return cleaned
