from fastapi import APIRouter

from app.api.routes.pdf.dependencies import (
    AdminDependency,
    AuthenticatedDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import to_pdf_model_setting_response
from app.api.schema_models.pdf import (
    ListPdfModelSettingsResponse,
    UpdatePdfModelSettingRequest,
)

router = APIRouter()


@router.get("/model-settings", response_model=ListPdfModelSettingsResponse)
def list_pdf_model_settings(
    service: PdfKnowledgeServiceDependency,
    _user: AuthenticatedDependency,
) -> ListPdfModelSettingsResponse:
    return ListPdfModelSettingsResponse(
        settings=[
            to_pdf_model_setting_response(setting) for setting in service.list_model_settings()
        ]
    )


@router.patch(
    "/model-settings/{setting_id}",
    response_model=ListPdfModelSettingsResponse,
)
def update_pdf_model_setting(
    setting_id: str,
    request: UpdatePdfModelSettingRequest,
    service: PdfKnowledgeServiceDependency,
    _admin: AdminDependency,
) -> ListPdfModelSettingsResponse:
    return ListPdfModelSettingsResponse(
        settings=[
            to_pdf_model_setting_response(setting)
            for setting in service.update_model_setting(
                setting_id=setting_id,
                selected_provider=request.selected_provider,
                selected_model=request.selected_model,
            )
        ]
    )
