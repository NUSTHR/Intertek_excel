from typing import Annotated

from fastapi import Depends

from app.api.dependencies import (
    get_current_user,
    get_pdf_chat_service,
    get_pdf_knowledge_service,
    require_admin_user,
)
from app.application.pdf_knowledge import PdfChatService, PdfKnowledgeService
from app.domain.models import AuthenticatedUser

PdfKnowledgeServiceDependency = Annotated[
    PdfKnowledgeService,
    Depends(get_pdf_knowledge_service),
]
PdfChatServiceDependency = Annotated[
    PdfChatService,
    Depends(get_pdf_chat_service),
]
AuthenticatedDependency = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminDependency = Annotated[AuthenticatedUser, Depends(require_admin_user)]
