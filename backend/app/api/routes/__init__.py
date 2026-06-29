"""Route modules for Excel Workspace."""

from app.api.routes import (
    auth,
    chat,
    document_summaries,
    excel_assets,
    health,
    pdf_knowledge,
    workspace,
)

__all__ = [
    "auth",
    "chat",
    "document_summaries",
    "excel_assets",
    "health",
    "pdf_knowledge",
    "workspace",
]
