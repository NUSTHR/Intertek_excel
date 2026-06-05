from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_document_summary_service
from app.api.schemas import DocumentSummaryResponse, SheetSummaryResponse
from app.application.document_summaries.service import DocumentSummaryService
from app.core.errors import AssetNotFoundError
from app.domain.models import DocumentSummary

router = APIRouter(prefix="/api/excel", tags=["document-summaries"])
DocumentSummaryServiceDependency = Annotated[
    DocumentSummaryService,
    Depends(get_document_summary_service),
]


@router.post(
    "/versions/{version_id}/summary/generate",
    response_model=DocumentSummaryResponse,
)
def generate_document_summary(
    version_id: str,
    service: DocumentSummaryServiceDependency,
) -> DocumentSummaryResponse:
    return _to_summary_response(service.generate_summary(version_id))


@router.get("/versions/{version_id}/summary", response_model=DocumentSummaryResponse)
def get_document_summary(
    version_id: str,
    service: DocumentSummaryServiceDependency,
) -> DocumentSummaryResponse:
    summary = service.get_summary(version_id)
    if summary is None:
        raise AssetNotFoundError("document summary was not found")
    return _to_summary_response(summary)


def _to_summary_response(summary: DocumentSummary) -> DocumentSummaryResponse:
    return DocumentSummaryResponse(
        summary_id=summary.summary_id,
        file_id=summary.file_id,
        version_id=summary.version_id,
        summary_text=summary.summary_text,
        business_domain=summary.business_domain,
        key_topics=summary.key_topics,
        suitable_questions=summary.suitable_questions,
        unsuitable_questions=summary.unsuitable_questions,
        sheet_summaries=[
            SheetSummaryResponse(
                sheet_id=sheet.sheet_id,
                sheet_name=sheet.sheet_name,
                summary=sheet.summary,
                important_columns=sheet.important_columns,
                likely_question_types=sheet.likely_question_types,
            )
            for sheet in summary.sheet_summaries
        ],
        created_at=summary.created_at,
    )
