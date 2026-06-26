from app.application.chat.access_control import ChatAccessController
from app.application.excel_assets.access import FileAccessContext
from app.core.errors import AssetNotFoundError
from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    ExcelCitation,
    SelectedDocument,
    UserRole,
)


class FakeExcelAssets:
    def __init__(
        self,
        *,
        hidden_file_ids: set[str] | None = None,
        deleted_file_ids: set[str] | None = None,
        deleted_version_ids: set[str] | None = None,
        legacy_version_ids: set[str] | None = None,
    ) -> None:
        self._hidden_file_ids = hidden_file_ids or set()
        self._deleted_file_ids = deleted_file_ids or set()
        self._deleted_version_ids = deleted_version_ids or set()
        self._legacy_version_ids = legacy_version_ids or set()

    def get_file(
        self,
        file_id: str,
        *,
        access: FileAccessContext | None = None,
    ) -> object:
        if file_id in self._deleted_file_ids:
            raise AssetNotFoundError("file not found")
        if (
            access is not None
            and not access.can_manage_files
            and file_id in self._hidden_file_ids
        ):
            raise AssetNotFoundError("file not found")
        return object()

    def list_sheets(
        self,
        version_id: str,
        *,
        access: FileAccessContext | None = None,
    ) -> list[object]:
        if version_id in self._deleted_version_ids:
            raise AssetNotFoundError("version not found")
        return [object()]

    def list_sheets_for_legacy_chat_context(self, version_id: str) -> list[object]:
        if version_id not in self._legacy_version_ids:
            raise AssetNotFoundError("legacy version not found")
        return [object()]


def member_access() -> FileAccessContext:
    return FileAccessContext(user_id="user_member", role=UserRole.MEMBER)


def admin_access() -> FileAccessContext:
    return FileAccessContext(user_id="user_admin", role=UserRole.ADMIN)


def selected_document(file_id: str, version_id: str = "version_1") -> SelectedDocument:
    return SelectedDocument(
        file_id=file_id,
        version_id=version_id,
        reason="test",
    )


def attached_document(file_id: str, version_id: str = "version_1") -> AttachedDocument:
    return AttachedDocument(
        session_id="session_1",
        file_id=file_id,
        version_id=version_id,
        attached_at="2026-01-01T00:00:00+00:00",
        row_count=1,
        context_hash="context_hash",
    )


def citation(file_id: str, version_id: str = "version_1") -> ExcelCitation:
    return ExcelCitation(
        citation_id=f"citation_{file_id}",
        evidence_id=f"{version_id}::sheet_1::row_1",
        file_id=file_id,
        version_id=version_id,
        sheet_id="sheet_1",
        sheet_name="Sheet1",
        row_id="row_1",
        row=["value"],
    )


def chat_turn(
    turn_id: str,
    *,
    selected_documents: list[SelectedDocument] | None = None,
    newly_attached_documents: list[SelectedDocument] | None = None,
    attached_documents: list[AttachedDocument] | None = None,
    citations: list[ExcelCitation] | None = None,
) -> ChatTurn:
    return ChatTurn(
        turn_id=turn_id,
        session_id="session_1",
        question="question",
        answer_text="answer",
        citation_ids=[],
        selected_documents=selected_documents or [],
        newly_attached_documents=newly_attached_documents or [],
        attached_documents=attached_documents or [],
        citations=citations or [],
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_admin_access_keeps_selected_and_attached_documents_unchanged() -> None:
    controller = ChatAccessController(
        FakeExcelAssets(hidden_file_ids={"hidden_file"})
    )
    selected = [selected_document("visible_file"), selected_document("hidden_file")]
    attached = [attached_document("visible_file"), attached_document("hidden_file")]

    assert (
        controller.filter_selected_documents(selected, access=admin_access())
        == selected
    )
    assert (
        controller.filter_attached_documents(attached, access=admin_access())
        == attached
    )


def test_member_access_filters_hidden_selected_and_attached_documents() -> None:
    controller = ChatAccessController(
        FakeExcelAssets(hidden_file_ids={"hidden_file"})
    )

    assert controller.filter_selected_documents(
        [selected_document("visible_file"), selected_document("hidden_file")],
        access=member_access(),
    ) == [selected_document("visible_file")]
    assert controller.filter_attached_documents(
        [attached_document("visible_file"), attached_document("hidden_file")],
        access=member_access(),
    ) == [attached_document("visible_file")]


def test_member_turn_context_keeps_or_drops_turns_from_all_document_sources() -> None:
    controller = ChatAccessController(
        FakeExcelAssets(hidden_file_ids={"hidden_file"})
    )
    accessible_turn = chat_turn(
        "turn_accessible",
        selected_documents=[selected_document("visible_file")],
        newly_attached_documents=[selected_document("visible_file")],
        attached_documents=[attached_document("visible_file")],
        citations=[citation("visible_file")],
    )
    inaccessible_turn = chat_turn(
        "turn_hidden",
        selected_documents=[selected_document("visible_file")],
        citations=[citation("hidden_file")],
    )
    context_free_turn = chat_turn("turn_without_file_context")

    assert controller.filter_turn_context(
        [accessible_turn, inaccessible_turn, context_free_turn],
        access=member_access(),
    ) == [accessible_turn, context_free_turn]


def test_deleted_legacy_document_remains_accessible_for_historical_chat_context() -> None:
    controller = ChatAccessController(
        FakeExcelAssets(
            deleted_file_ids={"deleted_file"},
            deleted_version_ids={"deleted_version"},
            legacy_version_ids={"deleted_version"},
        )
    )
    historical_document = selected_document("deleted_file", "deleted_version")

    assert controller.can_access_document(
        historical_document,
        access=member_access(),
    )


def test_deleted_non_legacy_document_is_filtered_from_attached_context() -> None:
    controller = ChatAccessController(
        FakeExcelAssets(
            deleted_file_ids={"deleted_file"},
            deleted_version_ids={"deleted_version"},
        )
    )
    historical_document = attached_document("deleted_file", "deleted_version")

    assert (
        controller.filter_attached_documents(
            [historical_document],
            access=member_access(),
        )
        == []
    )
