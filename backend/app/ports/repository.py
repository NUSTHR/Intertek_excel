from typing import Protocol

from app.domain.models import (
    AttachedDocument,
    ChatSession,
    ChatTurn,
    DocumentSummary,
    ExcelArtifact,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    ExcelVersionStatus,
    LlmPreference,
)


class ExcelAssetRepository(Protocol):
    def initialize(self) -> None:
        ...

    def create_file(self, file: ExcelFile) -> None:
        ...

    def get_file(self, file_id: str) -> ExcelFile | None:
        ...

    def find_file_by_display_name(self, display_name: str) -> ExcelFile | None:
        ...

    def list_files(self) -> list[ExcelFile]:
        ...

    def update_file_display_name(
        self,
        file_id: str,
        display_name: str,
        updated_at: str,
    ) -> ExcelFile | None:
        ...

    def delete_file(self, file_id: str) -> dict[str, int]:
        ...

    def create_version(self, version: ExcelFileVersion) -> None:
        ...

    def get_version(self, version_id: str) -> ExcelFileVersion | None:
        ...

    def list_versions(self, file_id: str) -> list[ExcelFileVersion]:
        ...

    def update_version_status(
        self,
        version_id: str,
        status: ExcelVersionStatus,
        error_message: str | None = None,
    ) -> None:
        ...

    def activate_version(self, file_id: str, version_id: str, activated_at: str) -> None:
        ...

    def create_sheet(self, sheet: ExcelSheet) -> None:
        ...

    def get_sheet(self, sheet_id: str) -> ExcelSheet | None:
        ...

    def list_sheets(self, version_id: str) -> list[ExcelSheet]:
        ...

    def create_artifact(self, artifact: ExcelArtifact) -> None:
        ...

    def list_artifacts(self, version_id: str) -> list[ExcelArtifact]:
        ...

    def create_row_mappings(self, mappings: list[ExcelRowMapping]) -> None:
        ...

    def get_row_mapping(
        self,
        sheet_id: str,
        row_id: str,
    ) -> ExcelRowMapping | None:
        ...

    def list_row_mappings_for_sheet(self, sheet_id: str) -> list[ExcelRowMapping]:
        ...


class DocumentSummaryRepository(Protocol):
    def initialize(self) -> None:
        ...

    def save_summary(self, summary: DocumentSummary) -> None:
        ...

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        ...

    def list_summaries(self) -> list[DocumentSummary]:
        ...


class ChatSessionRepository(Protocol):
    def initialize(self) -> None:
        ...

    def create_session(self, session: ChatSession) -> None:
        ...

    def list_sessions(self) -> list[ChatSession]:
        ...

    def get_session(self, session_id: str) -> ChatSession | None:
        ...

    def touch_session(self, session_id: str, updated_at: str) -> None:
        ...

    def rename_session(
        self,
        session_id: str,
        title: str,
        updated_at: str,
    ) -> ChatSession | None:
        ...

    def set_session_pinned(
        self,
        session_id: str,
        pinned_at: str | None,
        updated_at: str,
    ) -> ChatSession | None:
        ...

    def delete_session(self, session_id: str) -> bool:
        ...

    def attach_document(self, document: AttachedDocument) -> None:
        ...

    def list_attached_documents(self, session_id: str) -> list[AttachedDocument]:
        ...

    def create_turn(self, turn: ChatTurn) -> None:
        ...

    def list_turns(self, session_id: str) -> list[ChatTurn]:
        ...

    def get_llm_preference(self, scope: str) -> LlmPreference | None:
        ...

    def save_llm_preference(self, preference: LlmPreference) -> LlmPreference:
        ...
