from dataclasses import replace
from pathlib import Path

from app.application.pdf_knowledge.models import DeletePdfFileResult
from app.core.errors import (
    AssetNotFoundError,
    FileDeleteConfirmationRequiredError,
    FileNameConflictError,
    UploadValidationError,
)
from app.core.time import utc_now_iso
from app.domain.models import (
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfFileVisibility,
    UserRole,
)
from app.ports.repository import PdfKnowledgeRepository


class PdfLibraryService:
    """Owns PDF library access, metadata mutations, and document inspection."""

    def __init__(self, *, repository: PdfKnowledgeRepository) -> None:
        self._repository = repository

    def list_files(self, *, user_role: UserRole) -> list[PdfFile]:
        files = self._repository.list_pdf_files()
        if user_role == UserRole.ADMIN:
            return files
        return [
            file
            for file in files
            if file.visibility == PdfFileVisibility.VISIBLE
        ]

    def get_file(self, file_id: str, *, user_role: UserRole) -> PdfFile:
        file = self._repository.get_pdf_file(file_id)
        if file is None or (
            user_role != UserRole.ADMIN and file.visibility != PdfFileVisibility.VISIBLE
        ):
            raise AssetNotFoundError("PDF file was not found")
        return file

    def rename_file(
        self,
        file_id: str,
        display_name: str,
        *,
        user_role: UserRole,
    ) -> PdfFile:
        file = self.get_file(file_id, user_role=user_role)
        normalized_name = self._normalize_display_name(display_name)
        existing_file = self._repository.find_pdf_file_by_parent_and_name(
            user_id=file.user_id,
            parent_id=file.parent_id,
            display_name=normalized_name,
        )
        if existing_file is not None and existing_file.file_id != file.file_id:
            raise FileNameConflictError(
                display_name=normalized_name,
                file_id=existing_file.file_id,
            )
        updated_file = self._repository.update_pdf_file_display_name(
            file_id=file.file_id,
            display_name=normalized_name,
            updated_at=utc_now_iso(),
        )
        if updated_file is None:
            raise AssetNotFoundError("PDF file was not found")
        detail = self._repository.get_pdf_document_detail(updated_file.file_id)
        if detail is not None and detail.summary.status != "empty":
            self._repository.save_pdf_document_summary(
                replace(
                    detail.summary,
                    document_title=updated_file.display_name,
                    updated_at=updated_file.updated_at,
                )
            )
        return updated_file

    def set_file_visibility(
        self,
        file_id: str,
        visible_to_members: bool,
        *,
        user_role: UserRole,
    ) -> PdfFile:
        self.get_file(file_id, user_role=user_role)
        updated_file = self._repository.update_pdf_file_visibility(
            file_id=file_id,
            visibility=(
                PdfFileVisibility.VISIBLE
                if visible_to_members
                else PdfFileVisibility.HIDDEN
            ),
            updated_at=utc_now_iso(),
        )
        if updated_file is None:
            raise AssetNotFoundError("PDF file was not found")
        return updated_file

    def delete_file(
        self,
        file_id: str,
        *,
        confirm_delete: bool = False,
        user_role: UserRole,
    ) -> DeletePdfFileResult:
        file = self.get_file(file_id, user_role=user_role)
        if not confirm_delete:
            raise FileDeleteConfirmationRequiredError(
                display_name=file.display_name,
                file_id=file.file_id,
            )
        counts = self._repository.delete_pdf_file_tree(file_id)
        return DeletePdfFileResult(
            file_id=file.file_id,
            display_name=file.display_name,
            deleted_files=counts["deleted_files"],
            deleted_chunks=counts["deleted_chunks"],
            deleted_summaries=counts["deleted_summaries"],
            deleted_preview_blocks=counts["deleted_preview_blocks"],
            deleted_schema_items=counts["deleted_schema_items"],
            deleted_parse_reports=counts["deleted_parse_reports"],
            deleted_parse_pages=counts["deleted_parse_pages"],
            deleted_parse_artifacts=counts["deleted_parse_artifacts"],
        )

    def get_document_detail(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> PdfDocumentDetail:
        file = self.get_file(file_id, user_role=user_role)
        detail = self._repository.get_pdf_document_detail(file.file_id)
        if detail is not None:
            return detail
        return PdfDocumentDetail(
            file_id=file.file_id,
            summary=PdfDocumentSummary(file_id=file.file_id, status="empty", content=""),
            preview_blocks=[],
            schema=[],
            tags=[],
            parse_report=self._repository.get_pdf_parse_report(file.file_id),
        )

    def list_document_chunks(
        self,
        file_id: str,
        *,
        user_role: UserRole,
    ) -> list[PdfDocumentChunk]:
        file = self.get_file(file_id, user_role=user_role)
        return self._repository.list_pdf_document_chunks(file.file_id)

    def get_document_chunk(
        self,
        file_id: str,
        chunk_id: str,
        *,
        user_role: UserRole,
    ) -> PdfDocumentChunk:
        file = self.get_file(file_id, user_role=user_role)
        chunk = self._repository.get_pdf_document_chunk(file.file_id, chunk_id)
        if chunk is None:
            raise AssetNotFoundError("PDF document chunk was not found")
        return chunk

    def _normalize_display_name(self, filename: str) -> str:
        normalized = Path(filename).name.strip()
        if not normalized:
            raise UploadValidationError("PDF file name is required")
        return normalized[:255]
