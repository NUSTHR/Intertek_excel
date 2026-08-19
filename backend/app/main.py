from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import (
    get_pdf_summary_task_worker,
    get_pdf_upload_task_worker,
    get_pdf_vector_index_task_worker,
    get_upload_task_service,
    get_upload_task_worker,
)
from app.api.exception_handlers import register_exception_handlers
from app.api.routes import (
    auth,
    chat,
    document_summaries,
    excel_assets,
    health,
    pdf_knowledge,
    workspace,
)
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.upload_task_worker_enabled:
        upload_tasks = get_upload_task_service()
        upload_tasks.mark_stale_processing_tasks_failed(
            max_processing_age_minutes=settings.upload_task_stale_processing_minutes,
        )
        worker = get_upload_task_worker()
        worker.start()
    if settings.pdf_upload_task_worker_enabled:
        pdf_worker = get_pdf_upload_task_worker()
        pdf_worker.mark_stale_processing_tasks_failed(
            max_processing_age_minutes=settings.pdf_upload_task_stale_processing_minutes,
        )
        pdf_worker.start()
    if settings.pdf_summary_task_worker_enabled:
        pdf_summary_worker = get_pdf_summary_task_worker()
        pdf_summary_worker.mark_stale_running_tasks_failed(
            max_running_age_minutes=settings.pdf_summary_task_stale_running_minutes,
        )
        pdf_summary_worker.start()
    if settings.pdf_vector_indexing_active:
        get_pdf_vector_index_task_worker().start()
    try:
        yield
    finally:
        if settings.upload_task_worker_enabled:
            get_upload_task_worker().stop()
        if settings.pdf_upload_task_worker_enabled:
            get_pdf_upload_task_worker().stop()
        if settings.pdf_summary_task_worker_enabled:
            get_pdf_summary_task_worker().stop()
        if settings.pdf_vector_indexing_active:
            get_pdf_vector_index_task_worker().stop()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_runtime_safety()
    configure_logging(settings)
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(workspace.router)
    app.include_router(excel_assets.router)
    app.include_router(pdf_knowledge.router)
    app.include_router(document_summaries.router)
    app.include_router(chat.router)
    return app


app = create_app()
