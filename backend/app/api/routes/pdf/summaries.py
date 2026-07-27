from fastapi import APIRouter

from app.api.routes.pdf.dependencies import (
    AdminDependency,
    AuthenticatedDependency,
    PdfKnowledgeServiceDependency,
)
from app.api.routes.pdf.mappers import (
    to_pdf_summary_response,
    to_pdf_summary_task_response,
)
from app.api.schema_models.pdf import (
    CreatePdfSummaryTasksRequest,
    CreatePdfSummaryTasksResponse,
    GeneratePdfSummaryResponse,
    ListPdfSummaryTasksResponse,
    PdfSummaryTaskResponse,
)

router = APIRouter()


@router.post(
    "/summary-tasks",
    response_model=CreatePdfSummaryTasksResponse,
    status_code=202,
)
def create_pdf_summary_tasks(
    request: CreatePdfSummaryTasksRequest,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> CreatePdfSummaryTasksResponse:
    tasks = service.create_summary_tasks(
        user_id=user.user_id,
        user_role=user.role,
        file_ids=request.file_ids,
        parent_id=request.parent_id,
        include_descendants=request.include_descendants,
        force=request.force,
    )
    return CreatePdfSummaryTasksResponse(
        tasks=[to_pdf_summary_task_response(task) for task in tasks]
    )


@router.get("/summary-tasks", response_model=ListPdfSummaryTasksResponse)
def list_pdf_summary_tasks(
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> ListPdfSummaryTasksResponse:
    return ListPdfSummaryTasksResponse(
        tasks=[
            to_pdf_summary_task_response(task)
            for task in service.list_summary_tasks(user_id=user.user_id)
        ]
    )


@router.get("/summary-tasks/{task_id}", response_model=PdfSummaryTaskResponse)
def get_pdf_summary_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfSummaryTaskResponse:
    return to_pdf_summary_task_response(service.get_summary_task(task_id, user_id=user.user_id))


@router.post(
    "/summary-tasks/{task_id}/cancel",
    response_model=PdfSummaryTaskResponse,
)
def cancel_pdf_summary_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfSummaryTaskResponse:
    return to_pdf_summary_task_response(service.cancel_summary_task(task_id, user_id=user.user_id))


@router.post(
    "/summary-tasks/{task_id}/retry",
    response_model=PdfSummaryTaskResponse,
    status_code=202,
)
def retry_pdf_summary_task(
    task_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AdminDependency,
) -> PdfSummaryTaskResponse:
    return to_pdf_summary_task_response(service.retry_summary_task(task_id, user_id=user.user_id))


@router.post(
    "/files/{file_id}/summary/generate",
    response_model=GeneratePdfSummaryResponse,
)
def generate_pdf_document_summary(
    file_id: str,
    service: PdfKnowledgeServiceDependency,
    user: AuthenticatedDependency,
) -> GeneratePdfSummaryResponse:
    return GeneratePdfSummaryResponse(
        summary=to_pdf_summary_response(service.generate_summary(file_id, user_role=user.role))
    )
