from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.api.dependencies import (
    get_chat_service,
    get_document_summary_service,
    get_excel_asset_service,
)
from app.application.chat.service import ChatService
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    DocumentSummary,
    DraftAnswerBlock,
    DraftChatAnswer,
    DraftCitation,
    SelectedDocument,
)
from app.main import app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    excel_assets = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=OpenpyxlWorkbookReader(),
    )
    excel_assets.initialize()
    llm_client = FakeLlmClient()
    summaries = DocumentSummaryService(
        excel_assets=excel_assets,
        llm_client=llm_client,
        repository=repository,
    )
    chat = ChatService(
        excel_assets=excel_assets,
        summaries=summaries,
        llm_client=llm_client,
        sessions=repository,
    )
    app.dependency_overrides[get_excel_asset_service] = lambda: excel_assets
    app.dependency_overrides[get_document_summary_service] = lambda: summaries
    app.dependency_overrides[get_chat_service] = lambda: chat
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_summary_generation_and_chat_framework_flow(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)
    with workbook_path.open("rb") as workbook_file:
        upload_response = client.post(
            "/api/excel/files",
            files={
                "file": (
                    "standards.xlsx",
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert upload_response.status_code == 200
    version_id = upload_response.json()["version"]["version_id"]

    missing_summary_response = client.get(f"/api/excel/versions/{version_id}/summary")
    assert missing_summary_response.status_code == 404

    summary_response = client.post(f"/api/excel/versions/{version_id}/summary/generate")
    assert summary_response.status_code == 200
    assert summary_response.json()["version_id"] == version_id

    chat_response = client.post(
        "/api/excel/chat",
        json={"question": "What does the standards file contain?"},
    )

    assert chat_response.status_code == 200
    answer = chat_response.json()
    assert answer["selected_documents"][0]["version_id"] == version_id
    assert answer["answer_blocks"][0]["citation_ids"] == ["C1"]
    assert answer["citations"][0]["citation_id"] == "C1"
    assert answer["citations"][0]["row_id"] == "S001_R1"
    assert answer["citations"][0]["row"][1:] == ["Code", "Date"]


def test_chat_session_sends_all_rows_and_deduplicates_attached_file(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(tmp_path, llm_client) as client:
        workbook_path = tmp_path / "standards.xlsx"
        _write_large_xlsx_fixture(workbook_path, rows=220)
        with workbook_path.open("rb") as workbook_file:
            upload_response = client.post(
                "/api/excel/files",
                files={
                    "file": (
                        "standards.xlsx",
                        workbook_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        assert upload_response.status_code == 200
        version_id = upload_response.json()["version"]["version_id"]
        summary_response = client.post(f"/api/excel/versions/{version_id}/summary/generate")
        assert summary_response.status_code == 200

        session_response = client.post("/api/excel/chat/sessions")
        assert session_response.status_code == 200
        session_id = session_response.json()["session_id"]

        first_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/messages",
            json={"question": "What standards are listed?"},
        )
        assert first_response.status_code == 200
        first_answer = first_response.json()
        assert first_answer["session_id"] == session_id
        assert first_answer["newly_attached_documents"][0]["version_id"] == version_id
        assert first_answer["attached_documents"][0]["row_count"] == 221
        assert first_answer["citations"][0]["row_id"] == "S001_R205"
        assert len(llm_client.answer_calls[0]["rows"]) == 221

        second_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/messages",
            json={"question": "What is the date for that?"},
        )
        assert second_response.status_code == 200
        second_answer = second_response.json()
        assert second_answer["newly_attached_documents"] == []
        assert len(second_answer["attached_documents"]) == 1
        assert llm_client.route_calls[1]["user_questions"] == [
            "What standards are listed?",
            "What is the date for that?",
        ]
        assert len(llm_client.route_calls[1]["attached_documents"]) == 1
        assert len(llm_client.answer_calls[1]["previous_turns"]) == 1


def test_chat_route_returns_documents_before_answer_stage(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(tmp_path, llm_client) as client:
        workbook_path = tmp_path / "standards.xlsx"
        _write_large_xlsx_fixture(workbook_path, rows=5)
        with workbook_path.open("rb") as workbook_file:
            upload_response = client.post(
                "/api/excel/files",
                files={
                    "file": (
                        "standards.xlsx",
                        workbook_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
        version_id = upload_response.json()["version"]["version_id"]
        client.post(f"/api/excel/versions/{version_id}/summary/generate")
        session_id = client.post("/api/excel/chat/sessions").json()["session_id"]

        route_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/route",
            json={"question": "route first"},
        )
        assert route_response.status_code == 200
        route_payload = route_response.json()
        assert route_payload["selected_documents"][0]["version_id"] == version_id
        assert route_payload["newly_attached_documents"][0]["version_id"] == version_id
        assert route_payload["attached_documents"][0]["row_count"] == 6
        assert [timing["stage"] for timing in route_payload["timings"]] == [
            "route_model",
            "attach_documents",
            "route_total",
        ]
        assert llm_client.answer_calls == []

        answer_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/answer",
            json={"question": "route first"},
        )
        assert answer_response.status_code == 200
        answer_payload = answer_response.json()
        assert answer_payload["newly_attached_documents"] == []
        assert answer_payload["answer_blocks"][0]["citation_ids"] == ["C1"]
        assert {"load_rows", "answer_model", "verify_citations", "answer_total"}.issubset(
            {timing["stage"] for timing in answer_payload["timings"]}
        )


def _write_xlsx_fixture(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Standards"
    worksheet.append(["Code", "Date"])
    worksheet.append(["EN 60335-1:2023", "2024-01-01"])
    workbook.save(path)


def _write_large_xlsx_fixture(path: Path, rows: int) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Standards"
    worksheet.append(["Code", "Date"])
    for row_index in range(1, rows + 1):
        worksheet.append([f"EN 60335-{row_index}", f"2024-01-{row_index % 28 + 1:02d}"])
    workbook.save(path)


class CapturingLlmClient(FakeLlmClient):
    def __init__(self) -> None:
        self.route_calls: list[dict] = []
        self.answer_calls: list[dict] = []

    def route_documents(
        self,
        question: str,
        summaries: list[DocumentSummary],
        max_documents: int,
        user_questions: list[str] | None = None,
        attached_documents: list[AttachedDocument] | None = None,
    ) -> list[SelectedDocument]:
        self.route_calls.append(
            {
                "question": question,
                "user_questions": user_questions or [],
                "attached_documents": attached_documents or [],
            }
        )
        if not summaries:
            return []
        summary = summaries[0]
        return [
            SelectedDocument(
                file_id=summary.file_id,
                version_id=summary.version_id,
                reason="captured test selection",
                confidence=1.0,
            )
        ]

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
    ) -> DraftChatAnswer:
        self.answer_calls.append(
            {
                "question": question,
                "documents": documents,
                "rows": rows,
                "previous_turns": previous_turns or [],
            }
        )
        available_row_ids = {str(row["row_id"]) for row in rows}
        row_id = "S001_R205" if "S001_R205" in available_row_ids else str(rows[-1]["row_id"])
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=f"Captured answer for {question}.",
                    evidence_row_ids=[row_id],
                )
            ],
            citations=[DraftCitation(row_id=row_id, quote="captured row")],
            insufficient_evidence=False,
            follow_up_suggestions=[],
        )


@contextmanager
def _client_with_llm(tmp_path: Path, llm_client: FakeLlmClient) -> Iterator[TestClient]:
    repository = SQLiteExcelAssetRepository(tmp_path / "excel.sqlite3")
    excel_assets = ExcelAssetService(
        repository=repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=OpenpyxlWorkbookReader(),
    )
    excel_assets.initialize()
    summaries = DocumentSummaryService(
        excel_assets=excel_assets,
        llm_client=llm_client,
        repository=repository,
    )
    chat = ChatService(
        excel_assets=excel_assets,
        summaries=summaries,
        llm_client=llm_client,
        sessions=repository,
    )
    app.dependency_overrides[get_excel_asset_service] = lambda: excel_assets
    app.dependency_overrides[get_document_summary_service] = lambda: summaries
    app.dependency_overrides[get_chat_service] = lambda: chat
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
