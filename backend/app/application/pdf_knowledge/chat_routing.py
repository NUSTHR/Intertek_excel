from dataclasses import replace

from app.application.pdf_knowledge.chat_context import chunk_excerpt
from app.application.pdf_knowledge.chat_policy import PdfChatPolicy
from app.application.pdf_knowledge.chat_scope import dedupe_file_ids, is_visible_ready_pdf
from app.domain.models import (
    DocumentSummary,
    PdfDocumentChunk,
    PdfFile,
    SheetSummary,
    UserRole,
)
from app.ports.repository import PdfChatRepository


class PdfRoutingCatalogBuilder:
    def __init__(
        self,
        *,
        repository: PdfChatRepository,
        policy: PdfChatPolicy,
    ) -> None:
        self._repository = repository
        self._policy = policy

    def build(
        self,
        *,
        candidate_file_ids: list[str],
        user_role: UserRole,
    ) -> list[DocumentSummary]:
        allowed_file_ids = set(dedupe_file_ids(candidate_file_ids))
        files = {
            file.file_id: file
            for file in self._repository.list_pdf_files_by_ids(
                list(allowed_file_ids)
            )
            if file.file_id in allowed_file_ids
            and is_visible_ready_pdf(file, user_role)
        }
        ready_summaries = {
            summary.file_id: summary
            for summary in self._repository.list_pdf_document_summaries()
            if summary.status == "ready" and summary.file_id in files
        }
        fallback_file_ids = [
            file_id
            for file_id in candidate_file_ids
            if file_id in files and file_id not in ready_summaries
        ]
        chunks_by_file_id = self._repository.list_pdf_document_chunks_by_file_ids(
            fallback_file_ids
        )
        content_fingerprints = {
            file_id: file.content_fingerprint
            for file_id, file in files.items()
        }
        fingerprint_counts: dict[str, int] = {}
        for fingerprint in content_fingerprints.values():
            if fingerprint:
                fingerprint_counts[fingerprint] = (
                    fingerprint_counts.get(fingerprint, 0) + 1
                )

        routing_summaries: list[DocumentSummary] = []
        for file_id in candidate_file_ids:
            if file_id not in files:
                continue
            summary = (
                pdf_summary_to_document_summary(
                    summary=ready_summaries[file_id],
                    file=files[file_id],
                )
                if file_id in ready_summaries
                else fallback_pdf_routing_summary(
                    file=files[file_id],
                    chunks=chunks_by_file_id.get(file_id, []),
                    policy=self._policy,
                )
            )
            fingerprint = content_fingerprints.get(file_id, "")
            if fingerprint and fingerprint_counts.get(fingerprint, 0) > 1:
                summary = replace(
                    summary,
                    coverage_scope={
                        **summary.coverage_scope,
                        "duplicate_content_group": [fingerprint[:16]],
                    },
                )
            routing_summaries.append(summary)
        return routing_summaries


def pdf_summary_to_document_summary(
    *,
    summary,
    file: PdfFile,
) -> DocumentSummary:
    title = summary.document_title.strip() or file.display_name
    key_topics = summary.key_topics or [file.display_name]
    positive_terms = summary.positive_routing_terms or key_topics
    return DocumentSummary(
        summary_id=f"pdf-summary::{summary.file_id}",
        file_id=summary.file_id,
        version_id=summary.file_id,
        document_title=title,
        document_type=summary.document_type or "pdf_document",
        summary_text=summary.content,
        business_domain=summary.business_domain or "pdf knowledge",
        coverage_scope={"business_processes": ["pdf knowledge chat"]},
        key_topics=key_topics,
        positive_routing_terms=positive_terms,
        negative_routing_terms=summary.negative_routing_terms,
        exact_identifiers=summary.exact_identifiers or [file.display_name],
        suitable_questions=summary.suitable_questions,
        unsuitable_questions=summary.unsuitable_questions,
        sheet_summaries=[
            SheetSummary(
                sheet_id=summary.file_id,
                sheet_name=file.display_name,
                summary=summary.content,
                important_columns=[],
                likely_question_types=summary.suitable_questions,
                header_terms=positive_terms,
                sampled_identifiers=summary.exact_identifiers,
            )
        ],
        routing_notes=summary.routing_notes,
        created_at=summary.updated_at or file.updated_at,
    )


def fallback_pdf_routing_summary(
    *,
    file: PdfFile,
    chunks: list[PdfDocumentChunk],
    policy: PdfChatPolicy,
) -> DocumentSummary:
    sampled_chunks = evenly_sample_chunks(
        chunks,
        limit=policy.fallback_routing_sample_chunks,
    )
    titles = dedupe_text_values([chunk.title for chunk in sampled_chunks])
    excerpts = [
        chunk_excerpt(chunk.text)
        for chunk in sampled_chunks
        if chunk.text.strip()
    ]
    routing_terms = dedupe_text_values([file.display_name, *titles])
    summary_text = " | ".join([file.display_name, *titles, *excerpts])[
        : policy.max_fallback_routing_characters
    ]
    return DocumentSummary(
        summary_id=f"pdf-routing-fallback::{file.file_id}",
        file_id=file.file_id,
        version_id=file.file_id,
        document_title=file.display_name,
        document_type="pdf_document",
        summary_text=summary_text or file.display_name,
        business_domain="pdf knowledge",
        coverage_scope={"business_processes": ["pdf knowledge chat"]},
        key_topics=routing_terms,
        positive_routing_terms=routing_terms,
        negative_routing_terms=[],
        exact_identifiers=[file.display_name],
        suitable_questions=[],
        unsuitable_questions=[],
        sheet_summaries=[
            SheetSummary(
                sheet_id=file.file_id,
                sheet_name=file.display_name,
                summary=summary_text or file.display_name,
                important_columns=[],
                likely_question_types=[],
                header_terms=titles,
                sampled_identifiers=[file.display_name],
            )
        ],
        routing_notes="deterministic fallback routing card for a ready PDF without a summary",
        created_at=file.updated_at,
    )


def evenly_sample_chunks(
    chunks: list[PdfDocumentChunk],
    *,
    limit: int,
) -> list[PdfDocumentChunk]:
    if len(chunks) <= limit:
        return chunks
    if limit <= 1:
        return [chunks[0]]
    indexes = {
        round(index * (len(chunks) - 1) / (limit - 1))
        for index in range(limit)
    }
    return [chunks[index] for index in sorted(indexes)]


def dedupe_text_values(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        deduped.append(normalized)
    return deduped
