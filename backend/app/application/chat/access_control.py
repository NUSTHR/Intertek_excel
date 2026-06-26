from app.application.excel_assets.access import FileAccessContext
from app.application.excel_assets.service import ExcelAssetService
from app.core.errors import AssetNotFoundError
from app.domain.models import AttachedDocument, ChatTurn, SelectedDocument

ChatDocumentReference = SelectedDocument | AttachedDocument


class ChatAccessController:
    def __init__(self, excel_assets: ExcelAssetService) -> None:
        self._excel_assets = excel_assets

    def filter_attached_documents(
        self,
        documents: list[AttachedDocument],
        *,
        access: FileAccessContext | None,
    ) -> list[AttachedDocument]:
        if access is None or access.can_manage_files:
            return documents
        return [
            document
            for document in documents
            if self.can_access_document(document, access=access)
        ]

    def filter_selected_documents(
        self,
        documents: list[SelectedDocument],
        *,
        access: FileAccessContext | None,
    ) -> list[SelectedDocument]:
        if access is None or access.can_manage_files:
            return documents
        return [
            document
            for document in documents
            if self.can_access_file(document.file_id, access=access)
        ]

    def filter_turn_context(
        self,
        turns: list[ChatTurn],
        *,
        access: FileAccessContext | None,
    ) -> list[ChatTurn]:
        if access is None or access.can_manage_files:
            return turns
        return [
            turn
            for turn in turns
            if self.turn_context_is_accessible(turn, access=access)
        ]

    def turn_context_is_accessible(
        self,
        turn: ChatTurn,
        *,
        access: FileAccessContext,
    ) -> bool:
        file_ids = {
            document.file_id
            for document in [
                *turn.selected_documents,
                *turn.newly_attached_documents,
                *turn.attached_documents,
            ]
        }
        file_ids.update(citation.file_id for citation in turn.citations)
        if not file_ids:
            return True
        return all(self.can_access_file(file_id, access=access) for file_id in file_ids)

    def can_access_file(self, file_id: str, *, access: FileAccessContext) -> bool:
        try:
            self._excel_assets.get_file(file_id)
        except AssetNotFoundError:
            return True
        try:
            self._excel_assets.get_file(file_id, access=access)
        except AssetNotFoundError:
            return False
        return True

    def can_access_document(
        self,
        document: ChatDocumentReference,
        *,
        access: FileAccessContext,
    ) -> bool:
        if not self.can_access_file(document.file_id, access=access):
            return False
        try:
            self._excel_assets.list_sheets(document.version_id, access=access)
        except AssetNotFoundError:
            return self._can_use_deleted_legacy_document(document)
        return True

    def _can_use_deleted_legacy_document(self, document: ChatDocumentReference) -> bool:
        try:
            sheets = self._excel_assets.list_sheets_for_legacy_chat_context(
                document.version_id
            )
        except AssetNotFoundError:
            return False
        return any(sheets)
