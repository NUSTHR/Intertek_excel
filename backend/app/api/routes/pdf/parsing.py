from fastapi import APIRouter

from app.api.routes.pdf.dependencies import (
    AdminDependency,
    AuthenticatedDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import (
    to_pdf_parser_profile_response,
    to_pdf_upload_task_response,
)
from app.api.schema_models.pdf import (
    ListPdfParserProfilesResponse,
    PdfParserStatusResponse,
    PdfUploadTaskResponse,
    UpdatePdfParserProfileRequest,
)

router = APIRouter()


@router.get("/parser/status", response_model=PdfParserStatusResponse)
def get_pdf_parser_status(
    service: PdfKnowledgeServiceDependency,
    _user: AuthenticatedDependency,
) -> PdfParserStatusResponse:
    status = service.get_parser_status()
    return PdfParserStatusResponse(
        backend=status.backend,
        available=status.available,
        command=status.command,
        version=status.version,
        detail=status.detail,
    )


@router.get("/parser/profiles", response_model=ListPdfParserProfilesResponse)
def list_pdf_parser_profiles(
    service: PdfKnowledgeServiceDependency,
    _user: AuthenticatedDependency,
) -> ListPdfParserProfilesResponse:
    return _parser_profiles_response(service.list_parser_profiles())


@router.patch("/parser/profiles", response_model=ListPdfParserProfilesResponse)
def update_pdf_parser_profile(
    request: UpdatePdfParserProfileRequest,
    service: PdfKnowledgeServiceDependency,
    _user: AdminDependency,
) -> ListPdfParserProfilesResponse:
    return _parser_profiles_response(service.select_parser_profile(request.selected_profile_id))


@router.post(
    "/files/{file_id}/reparse",
    response_model=PdfUploadTaskResponse,
    status_code=202,
)
def reparse_pdf_document(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfUploadTaskResponse:
    return to_pdf_upload_task_response(
        service.create_reparse_task(
            file_id=file_id,
            user_id=user.user_id,
            user_role=user.role,
        )
    )


def _parser_profiles_response(profiles) -> ListPdfParserProfilesResponse:
    selected = next(
        (profile.profile_id for profile in profiles if profile.is_selected),
        "",
    )
    return ListPdfParserProfilesResponse(
        selected_profile_id=selected,
        profiles=[to_pdf_parser_profile_response(profile) for profile in profiles],
    )
