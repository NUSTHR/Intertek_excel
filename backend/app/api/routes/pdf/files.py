from typing import Annotated

from fastapi import APIRouter, Query

from app.api.routes.pdf.dependencies import (
    AdminDependency,
    AuthenticatedDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import (
    to_delete_pdf_file_response,
    to_pdf_document_chunk_response,
    to_pdf_document_detail_response,
    to_pdf_file_response,
)
from app.api.schema_models.pdf import (
    DeletePdfFileResponse,
    ListPdfDocumentChunksResponse,
    ListPdfFilesResponse,
    PdfDocumentDetailResponse,
    PdfFileResponse,
    RenamePdfFileRequest,
    SetPdfFileVisibilityRequest,
)

router = APIRouter()


@router.get("/files", response_model=ListPdfFilesResponse)
def list_pdf_files(
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> ListPdfFilesResponse:
    return ListPdfFilesResponse(
        files=[to_pdf_file_response(file) for file in service.list_files(user_role=user.role)]
    )


@router.get("/files/{file_id}", response_model=PdfFileResponse)
def get_pdf_file(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> PdfFileResponse:
    return to_pdf_file_response(service.get_file(file_id, user_role=user.role))


@router.patch("/files/{file_id}", response_model=PdfFileResponse)
def rename_pdf_file(
    file_id: str,
    request: RenamePdfFileRequest,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfFileResponse:
    return to_pdf_file_response(
        service.rename_file(
            file_id,
            request.display_name,
            user_role=user.role,
        )
    )


@router.patch("/files/{file_id}/visibility", response_model=PdfFileResponse)
def set_pdf_file_visibility(
    file_id: str,
    request: SetPdfFileVisibilityRequest,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfFileResponse:
    return to_pdf_file_response(
        service.set_file_visibility(
            file_id,
            visible_to_members=request.visible_to_members,
            user_role=user.role,
        )
    )


@router.delete("/files/{file_id}", response_model=DeletePdfFileResponse)
def delete_pdf_file(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
    confirm_delete: Annotated[bool, Query()] = False,
) -> DeletePdfFileResponse:
    return to_delete_pdf_file_response(
        service.delete_file(
            file_id,
            confirm_delete=confirm_delete,
            user_role=user.role,
        )
    )


@router.get("/files/{file_id}/detail", response_model=PdfDocumentDetailResponse)
def get_pdf_document_detail(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> PdfDocumentDetailResponse:
    return to_pdf_document_detail_response(
        service.get_document_detail(file_id, user_role=user.role)
    )


@router.get("/files/{file_id}/chunks", response_model=ListPdfDocumentChunksResponse)
def list_pdf_document_chunks(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> ListPdfDocumentChunksResponse:
    return ListPdfDocumentChunksResponse(
        chunks=[
            to_pdf_document_chunk_response(chunk)
            for chunk in service.list_document_chunks(file_id, user_role=user.role)
        ]
    )
