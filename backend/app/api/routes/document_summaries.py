from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    get_current_user,
    get_document_summary_service,
    require_admin_user,
)
from app.api.schemas import (
    DocumentSummaryResponse,
    GenerateDocumentSummaryRequest,
    SheetSummaryResponse,
    SheetSummaryUpdateRequest,
    UpdateDocumentSummaryRequest,
)
from app.application.document_summaries.service import DocumentSummaryService
from app.core.errors import AssetNotFoundError
from app.domain.models import DocumentSummary, SheetSummary

router = APIRouter(prefix="/api/excel", tags=["document-summaries"])
DocumentSummaryServiceDependency = Annotated[
    DocumentSummaryService,
    Depends(get_document_summary_service),
]
AuthenticatedDependency = Annotated[object, Depends(get_current_user)]
AdminDependency = Annotated[object, Depends(require_admin_user)]


@router.post(
    "/versions/{version_id}/summary/generate",
    response_model=DocumentSummaryResponse,
)
def generate_document_summary(
    version_id: str,
    service: DocumentSummaryServiceDependency,
    _admin: AdminDependency,
    request: GenerateDocumentSummaryRequest | None = None,
) -> DocumentSummaryResponse:
    model = request.model if request is not None else None
    provider = request.provider if request is not None else None
    return _to_summary_response(
        service.generate_summary(version_id, model=model, provider=provider)
    )


@router.get("/versions/{version_id}/summary", response_model=DocumentSummaryResponse)
def get_document_summary(
    version_id: str,
    service: DocumentSummaryServiceDependency,
    _user: AuthenticatedDependency,
) -> DocumentSummaryResponse:
    summary = service.get_summary(version_id)
    if summary is None:
        raise AssetNotFoundError("document summary was not found")
    return _to_summary_response(summary)


@router.patch("/versions/{version_id}/summary", response_model=DocumentSummaryResponse)
def update_document_summary(
    version_id: str,
    request: UpdateDocumentSummaryRequest,
    service: DocumentSummaryServiceDependency,
    _admin: AdminDependency,
) -> DocumentSummaryResponse:
    return _to_summary_response(
        service.update_summary(
            version_id,
            document_title=request.document_title,
            summary_text=request.summary_text,
            business_domain=request.business_domain,
            key_topics=request.key_topics,
            positive_routing_terms=request.positive_routing_terms,
            negative_routing_terms=request.negative_routing_terms,
            exact_identifiers=request.exact_identifiers,
            suitable_questions=request.suitable_questions,
            unsuitable_questions=request.unsuitable_questions,
            sheet_summaries=(
                [_to_sheet_summary(sheet) for sheet in request.sheet_summaries]
                if request.sheet_summaries is not None
                else None
            ),
            routing_notes=request.routing_notes,
        )
    )


def _to_sheet_summary(sheet: SheetSummaryUpdateRequest) -> SheetSummary:
    return SheetSummary(
        sheet_id=sheet.sheet_id,
        sheet_name=sheet.sheet_name,
        summary=sheet.summary,
        important_columns=sheet.important_columns,
        likely_question_types=sheet.likely_question_types,
        header_terms=sheet.header_terms,
        sampled_identifiers=sheet.sampled_identifiers,
    )


def _to_summary_response(summary: DocumentSummary) -> DocumentSummaryResponse:
    return DocumentSummaryResponse(
        summary_id=summary.summary_id,
        file_id=summary.file_id,
        version_id=summary.version_id,
        document_title=summary.document_title,
        document_type=summary.document_type,
        summary_text=summary.summary_text,
        business_domain=summary.business_domain,
        coverage_scope=summary.coverage_scope,
        key_topics=summary.key_topics,
        positive_routing_terms=summary.positive_routing_terms,
        negative_routing_terms=summary.negative_routing_terms,
        exact_identifiers=summary.exact_identifiers,
        suitable_questions=summary.suitable_questions,
        unsuitable_questions=summary.unsuitable_questions,
        sheet_summaries=[
            SheetSummaryResponse(
                sheet_id=sheet.sheet_id,
                sheet_name=sheet.sheet_name,
                summary=sheet.summary,
                important_columns=sheet.important_columns,
                likely_question_types=sheet.likely_question_types,
                header_terms=sheet.header_terms,
                sampled_identifiers=sheet.sampled_identifiers,
            )
            for sheet in summary.sheet_summaries
        ],
        routing_notes=summary.routing_notes,
        created_at=summary.created_at,
    )
