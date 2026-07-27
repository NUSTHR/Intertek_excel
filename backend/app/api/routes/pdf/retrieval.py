from fastapi import APIRouter

from app.api.routes.pdf.dependencies import (
    AuthenticatedDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import to_pdf_chunk_search_match_response
from app.api.schema_models.pdf import SearchPdfChunksRequest, SearchPdfChunksResponse

router = APIRouter()


@router.post("/retrieval/search", response_model=SearchPdfChunksResponse)
def search_pdf_document_chunks(
    request: SearchPdfChunksRequest,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> SearchPdfChunksResponse:
    result = service.search_document_chunks(
        query=request.query,
        file_ids=request.file_ids,
        limit=request.limit,
        user_role=user.role,
    )
    return SearchPdfChunksResponse(
        query=result.query,
        matches=[to_pdf_chunk_search_match_response(match) for match in result.matches],
        total_matches=result.total_matches,
        limit=result.limit,
    )
