from fastapi import APIRouter

from app.api.routes.pdf import (
    chat,
    files,
    parsing,
    retrieval,
    settings,
    summaries,
    uploads,
)

router = APIRouter(prefix="/api/pdf", tags=["pdf-knowledge"])
router.include_router(parsing.router)
router.include_router(uploads.router)
router.include_router(summaries.router)
router.include_router(retrieval.router)
router.include_router(chat.router)
router.include_router(settings.router)
router.include_router(files.router)
