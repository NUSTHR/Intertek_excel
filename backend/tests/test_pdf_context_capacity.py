from pathlib import Path

import pytest

from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.application.pdf_knowledge.chat_context import PdfContextAssembler
from app.application.pdf_knowledge.chat_policy import PdfChatPolicy
from app.core.errors import PdfAnswerContextTooLarge
from app.domain.models import (
    PdfDocumentChunk,
    PdfFile,
    PdfFileKind,
    PdfFileStatus,
    PdfFileVisibility,
    PdfProcessingStatus,
    SelectedDocument,
    UserRole,
)


def _repository_with_large_context(tmp_path: Path) -> SQLiteExcelAssetRepository:
    repository = SQLiteExcelAssetRepository(tmp_path / "context-capacity.sqlite3")
    repository.initialize()
    repository.create_pdf_file(
        PdfFile(
            file_id="file-1",
            user_id="user-1",
            parent_id=None,
            display_name="large.pdf",
            original_filename="large.pdf",
            kind=PdfFileKind.PDF,
            size_bytes=100,
            storage_path="pdf-knowledge/files/file-1/large.pdf",
            status=PdfFileStatus.ACTIVE,
            visibility=PdfFileVisibility.VISIBLE,
            processing_status=PdfProcessingStatus.READY,
            progress=100,
            status_detail="Ready.",
            error_message=None,
            page_count=1,
            chunk_count=1,
            created_at="2026-08-14T00:00:00+00:00",
            updated_at="2026-08-14T00:00:00+00:00",
            content_fingerprint="fingerprint-1",
        )
    )
    repository.replace_pdf_document_chunks(
        "file-1",
        [
            PdfDocumentChunk(
                chunk_id="chunk-1",
                file_id="file-1",
                chunk_index=0,
                text="0123456789ABCDEF",
                page_label="1",
                title="Large",
                token_count=8,
                content_hash="hash-1",
            )
        ],
    )
    return repository


def test_full_document_context_fails_closed_instead_of_truncating(
    tmp_path: Path,
) -> None:
    assembler = PdfContextAssembler(
        repository=_repository_with_large_context(tmp_path),
        policy=PdfChatPolicy(
            full_document_context=True,
            max_answer_context_chunks=10,
            max_answer_context_characters=10,
            max_answer_context_tokens=100,
        ),
    )

    with pytest.raises(PdfAnswerContextTooLarge) as captured:
        assembler.assemble(
            documents=[
                SelectedDocument(
                    file_id="file-1",
                    version_id="file-1",
                    reason="selected",
                )
            ],
            user_role=UserRole.ADMIN,
        )

    error = captured.value
    assert error.character_count == 16
    assert error.max_characters == 10
    assert error.retryable is False
