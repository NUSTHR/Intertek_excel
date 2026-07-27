from app.api.schema_models.common import ChatSessionResponse
from app.api.schema_models.pdf import (
    DeletePdfFileResponse,
    PdfAttachedDocumentResponse,
    PdfChatAnswerBlockResponse,
    PdfChatAnswerResponse,
    PdfChatRouteResponse,
    PdfChatTurnResponse,
    PdfChunkSearchMatchResponse,
    PdfCitationResponse,
    PdfDocumentChunkResponse,
    PdfDocumentDetailResponse,
    PdfDocumentSummaryResponse,
    PdfFileResponse,
    PdfModelSettingResponse,
    PdfParseArtifactResponse,
    PdfParsePageResponse,
    PdfParseReportResponse,
    PdfParserProfileResponse,
    PdfPreviewBlockResponse,
    PdfSchemaItemResponse,
    PdfSelectedDocumentResponse,
    PdfSummaryTaskResponse,
    PdfUploadBatchResponse,
    PdfUploadTaskResponse,
)
from app.application.pdf_knowledge.models import (
    DeletePdfFileResult,
    PdfChatAnswer,
    PdfChunkSearchMatch,
    PdfCitation,
)
from app.domain.models import (
    ChatSession,
    ChatTurn,
    PdfAttachedDocument,
    PdfChatRouteResult,
    PdfDocumentChunk,
    PdfDocumentDetail,
    PdfDocumentSummary,
    PdfFile,
    PdfModelSetting,
    PdfParseReport,
    PdfSummaryTask,
    PdfUploadBatch,
    PdfUploadTask,
    PdfUploadTaskStatus,
    SelectedDocument,
)
from app.ports.pdf_parser import PdfParserProfile


def to_pdf_file_response(file: PdfFile) -> PdfFileResponse:
    return PdfFileResponse(
        file_id=file.file_id,
        parent_id=file.parent_id,
        kind=file.kind.value,
        display_name=file.display_name,
        original_filename=file.original_filename,
        size_bytes=file.size_bytes,
        status=file.status.value,
        processing_status=file.processing_status.value,
        progress=file.progress,
        status_detail=file.status_detail,
        error_message=file.error_message,
        page_count=file.page_count,
        chunk_count=file.chunk_count,
        quality_status=file.quality_status.value if file.quality_status else None,
        coverage_ratio=file.coverage_ratio,
        warning_count=file.warning_count,
        failed_page_count=file.failed_page_count,
        parser_backend=file.parser_backend,
        created_at=file.created_at,
        updated_at=file.updated_at,
        visible_to_members=file.visibility.value == "visible",
    )


def to_delete_pdf_file_response(
    result: DeletePdfFileResult,
) -> DeletePdfFileResponse:
    return DeletePdfFileResponse(
        file_id=result.file_id,
        display_name=result.display_name,
        deleted_files=result.deleted_files,
        deleted_chunks=result.deleted_chunks,
        deleted_summaries=result.deleted_summaries,
        deleted_preview_blocks=result.deleted_preview_blocks,
        deleted_schema_items=result.deleted_schema_items,
        deleted_parse_reports=result.deleted_parse_reports,
        deleted_parse_pages=result.deleted_parse_pages,
        deleted_parse_artifacts=result.deleted_parse_artifacts,
    )


def to_session_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        title=session.title,
        pinned_at=session.pinned_at,
        status=session.status,
    )


def to_pdf_parser_profile_response(
    profile: PdfParserProfile,
) -> PdfParserProfileResponse:
    return PdfParserProfileResponse(
        id=profile.profile_id,
        label=profile.label,
        kind=profile.kind,
        backend=profile.status.backend,
        available=profile.status.available,
        command=profile.status.command,
        version=profile.status.version,
        detail=profile.status.detail,
        description=profile.description,
        is_default=profile.is_default,
        is_selected=profile.is_selected,
    )


def to_pdf_upload_task_response(task: PdfUploadTask) -> PdfUploadTaskResponse:
    return PdfUploadTaskResponse(
        task_id=task.task_id,
        file_id=task.file_id,
        batch_id=task.batch_id,
        original_filename=task.original_filename,
        status=_task_status_for_ui(task),
        stage=task.stage.value,
        progress=task.progress,
        detail=task.detail,
        error_message=task.error_message,
        error_code=task.error_code,
        parser_backend=task.parser_backend,
        retry_count=task.retry_count,
        result=task.result,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        last_retry_at=task.last_retry_at,
    )


def to_pdf_summary_task_response(task: PdfSummaryTask) -> PdfSummaryTaskResponse:
    return PdfSummaryTaskResponse(
        task_id=task.task_id,
        file_id=task.file_id,
        status=task.status.value,
        progress=task.progress,
        detail=task.detail,
        error_message=task.error_message,
        retry_count=task.retry_count,
        result=task.result,
        created_at=task.created_at,
        updated_at=task.updated_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        last_retry_at=task.last_retry_at,
    )


def to_pdf_upload_batch_response(batch: PdfUploadBatch) -> PdfUploadBatchResponse:
    return PdfUploadBatchResponse(
        batch_id=batch.batch_id,
        source_name=batch.source_name,
        status=batch.status.value,
        total_files=batch.total_files,
        accepted_files=batch.accepted_files,
        skipped_files=batch.skipped_files,
        total_bytes=batch.total_bytes,
        progress=batch.progress,
        detail=batch.detail,
        error_message=batch.error_message,
        parser_backend=batch.parser_backend,
        result=batch.result,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        completed_at=batch.completed_at,
    )


def _task_status_for_ui(task: PdfUploadTask) -> str:
    if task.status == PdfUploadTaskStatus.CANCELLED:
        return "cancelled"
    if task.status == PdfUploadTaskStatus.PROCESSING:
        if task.stage.value in {"parsing", "indexing"}:
            return task.stage.value
        if task.progress >= 90:
            return "indexing"
        return "parsing"
    return task.status.value


def to_pdf_document_detail_response(
    detail: PdfDocumentDetail,
) -> PdfDocumentDetailResponse:
    return PdfDocumentDetailResponse(
        file_id=detail.file_id,
        summary=to_pdf_summary_response(detail.summary),
        preview_blocks=[
            PdfPreviewBlockResponse(
                block_id=block.block_id,
                page_label=block.page_label,
                title=block.title,
                content=block.content,
            )
            for block in detail.preview_blocks
        ],
        schema=[
            PdfSchemaItemResponse(
                item_id=item.item_id,
                label=item.label,
                value=item.value,
            )
            for item in detail.schema
        ],
        tags=detail.tags,
        parse_report=(
            to_pdf_parse_report_response(detail.parse_report)
            if detail.parse_report is not None
            else None
        ),
    )


def to_pdf_parse_report_response(
    report: PdfParseReport,
) -> PdfParseReportResponse:
    return PdfParseReportResponse(
        file_id=report.file_id,
        parser_backend=report.parser_backend,
        parser_version=report.parser_version,
        quality_status=report.quality_status.value,
        total_pages=report.total_pages,
        parsed_pages=report.parsed_pages,
        failed_pages=report.failed_pages,
        empty_pages=report.empty_pages,
        text_block_count=report.text_block_count,
        table_block_count=report.table_block_count,
        image_block_count=report.image_block_count,
        chunk_count=report.chunk_count,
        coverage_ratio=report.coverage_ratio,
        warning_count=report.warning_count,
        error_count=report.error_count,
        warnings=report.warnings,
        started_at=report.started_at,
        finished_at=report.finished_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
        pages=[
            PdfParsePageResponse(
                page_id=page.page_id,
                page_number=page.page_number,
                page_label=page.page_label,
                status=page.status.value,
                text_block_count=page.text_block_count,
                table_block_count=page.table_block_count,
                image_block_count=page.image_block_count,
                char_count=page.char_count,
                warning_message=page.warning_message,
                error_message=page.error_message,
            )
            for page in report.pages
        ],
        artifacts=[
            PdfParseArtifactResponse(
                artifact_id=artifact.artifact_id,
                artifact_type=artifact.artifact_type,
                name=artifact.name,
                path=artifact.path,
                size_bytes=artifact.size_bytes,
                content_hash=artifact.content_hash,
                created_at=artifact.created_at,
            )
            for artifact in report.artifacts
        ],
    )


def to_pdf_document_chunk_response(
    chunk: PdfDocumentChunk,
) -> PdfDocumentChunkResponse:
    return PdfDocumentChunkResponse(
        chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        page_label=chunk.page_label,
        title=chunk.title,
        token_count=chunk.token_count,
        content_hash=chunk.content_hash,
        metadata=chunk.metadata,
    )


def to_pdf_chunk_search_match_response(
    match: PdfChunkSearchMatch,
) -> PdfChunkSearchMatchResponse:
    return PdfChunkSearchMatchResponse(
        file=to_pdf_file_response(match.file),
        chunk=to_pdf_document_chunk_response(match.chunk),
        score=match.score,
        excerpt=match.excerpt,
        matched_terms=match.matched_terms,
    )


def to_pdf_chat_answer_response(answer: PdfChatAnswer) -> PdfChatAnswerResponse:
    return PdfChatAnswerResponse(
        session_id=answer.session_id,
        question=answer.question,
        answer_blocks=[
            PdfChatAnswerBlockResponse(
                text=block.text,
                citation_ids=block.citation_ids,
                reasoning=block.reasoning,
            )
            for block in answer.answer_blocks
        ],
        citations=[to_pdf_citation_response(citation) for citation in answer.citations],
        retrieval_matches=[
            to_pdf_chunk_search_match_response(match) for match in answer.retrieval_matches
        ],
        selected_documents=[
            to_pdf_selected_document_response(document) for document in answer.selected_documents
        ],
        newly_attached_documents=[
            to_pdf_selected_document_response(document)
            for document in answer.newly_attached_documents
        ],
        attached_documents=[
            to_pdf_attached_document_response(document) for document in answer.attached_documents
        ],
        insufficient_evidence=answer.insufficient_evidence,
        follow_up_suggestions=answer.follow_up_suggestions,
        warnings=answer.warnings,
        created_at=answer.created_at,
    )


def to_pdf_chat_route_response(
    route_result: PdfChatRouteResult,
) -> PdfChatRouteResponse:
    return PdfChatRouteResponse(
        session_id=route_result.session_id,
        question=route_result.question,
        selected_documents=[
            to_pdf_selected_document_response(document)
            for document in route_result.selected_documents
        ],
        newly_attached_documents=[
            to_pdf_selected_document_response(document)
            for document in route_result.newly_attached_documents
        ],
        attached_documents=[
            to_pdf_attached_document_response(document)
            for document in route_result.attached_documents
        ],
        created_at=route_result.created_at,
    )


def to_pdf_chat_turn_response(turn: ChatTurn) -> PdfChatTurnResponse:
    return PdfChatTurnResponse(
        turn_id=turn.turn_id,
        session_id=turn.session_id,
        question=turn.question,
        answer=PdfChatAnswerResponse(
            session_id=turn.session_id,
            question=turn.question,
            answer_blocks=[
                PdfChatAnswerBlockResponse(
                    text=block.text,
                    citation_ids=block.citation_ids,
                    reasoning=block.reasoning,
                )
                for block in turn.answer_blocks
            ],
            citations=[
                to_pdf_citation_response(_pdf_citation_from_stored_citation(citation))
                for citation in turn.citations
            ],
            retrieval_matches=[],
            selected_documents=[
                to_pdf_selected_document_response(document) for document in turn.selected_documents
            ],
            newly_attached_documents=[
                to_pdf_selected_document_response(document)
                for document in turn.newly_attached_documents
            ],
            attached_documents=[
                to_pdf_attached_document_response(
                    _pdf_attached_document_from_stored_document(document)
                )
                for document in turn.attached_documents
            ],
            insufficient_evidence=turn.insufficient_evidence,
            follow_up_suggestions=turn.follow_up_suggestions,
            warnings=turn.warnings,
            created_at=turn.created_at,
        ),
        created_at=turn.created_at,
    )


def to_pdf_citation_response(citation: PdfCitation) -> PdfCitationResponse:
    return PdfCitationResponse(
        citation_id=citation.citation_id,
        evidence_id=citation.evidence_id,
        file_id=citation.file_id,
        file_name=citation.file_name,
        chunk_id=citation.chunk_id,
        chunk_index=citation.chunk_index,
        page_label=citation.page_label,
        title=citation.title,
        quote=citation.quote,
    )


def to_pdf_selected_document_response(
    document: SelectedDocument,
) -> PdfSelectedDocumentResponse:
    return PdfSelectedDocumentResponse(
        file_id=document.file_id,
        version_id=document.version_id,
        reason=document.reason,
        confidence=document.confidence,
    )


def to_pdf_attached_document_response(
    document: PdfAttachedDocument,
) -> PdfAttachedDocumentResponse:
    return PdfAttachedDocumentResponse(
        file_id=document.file_id,
        attached_at=document.attached_at,
        chunk_count=document.chunk_count,
        context_hash=document.context_hash,
        status=document.status,
    )


def _pdf_citation_from_stored_citation(citation) -> PdfCitation:
    return PdfCitation(
        citation_id=citation.citation_id,
        evidence_id=citation.evidence_id,
        file_id=citation.file_id,
        file_name=citation.row[0] if len(citation.row) >= 1 else citation.file_id,
        chunk_id=citation.version_id,
        chunk_index=_safe_int(citation.row_id),
        page_label=citation.row[1] if len(citation.row) >= 2 else None,
        title=citation.sheet_name,
        quote=citation.quote,
    )


def _pdf_attached_document_from_stored_document(document) -> PdfAttachedDocument:
    return PdfAttachedDocument(
        session_id=document.session_id,
        file_id=document.file_id,
        attached_at=document.attached_at,
        chunk_count=document.row_count,
        context_hash=document.context_hash,
        status=document.status,
    )


def to_pdf_summary_response(
    summary: PdfDocumentSummary,
) -> PdfDocumentSummaryResponse:
    return PdfDocumentSummaryResponse(
        file_id=summary.file_id,
        status=summary.status,
        content=summary.content,
        updated_at=summary.updated_at,
        error_message=summary.error_message,
        document_title=summary.document_title,
        document_type=summary.document_type,
        business_domain=summary.business_domain,
        key_topics=summary.key_topics,
        positive_routing_terms=summary.positive_routing_terms,
        negative_routing_terms=summary.negative_routing_terms,
        exact_identifiers=summary.exact_identifiers,
        suitable_questions=summary.suitable_questions,
        unsuitable_questions=summary.unsuitable_questions,
        routing_notes=summary.routing_notes,
    )


def to_pdf_model_setting_response(
    setting: PdfModelSetting,
) -> PdfModelSettingResponse:
    return PdfModelSettingResponse(
        id=setting.setting_id,
        label=setting.label,
        providers=setting.providers,
        models=setting.models,
        selected_provider=setting.selected_provider,
        selected_model=setting.selected_model,
    )


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
