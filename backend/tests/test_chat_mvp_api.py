from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.adapters.dialogue import LangGraphChatWorkflow
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
from app.core.errors import LlmRequestError
from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    DocumentSummary,
    DraftAnswerBlock,
    DraftChatAnswer,
    DraftCitation,
    ExcelCitation,
    SelectedDocument,
)
from app.main import app
from app.ports.chat_workflow import ChatWorkflow


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
    assert (
        answer["citations"][0]["evidence_id"]
        == f"{version_id}::{answer['citations'][0]['sheet_id']}::S001_R1"
    )
    assert answer["citations"][0]["row_id"] == "S001_R1"
    assert answer["citations"][0]["row"][1:] == ["Code", "Date"]


def test_llm_request_error_returns_user_safe_api_error(tmp_path: Path) -> None:
    class FailingSummaryLlmClient(FakeLlmClient):
        def generate_document_summary(self, profile, *, model=None, provider=None):
            _ = profile, model, provider
            raise LlmRequestError(
                stage="summary",
                model="private-model",
                duration_seconds=1.25,
                cause=RuntimeError("provider secret failure"),
            )

    workbook_path = tmp_path / "standards.xlsx"
    _write_xlsx_fixture(workbook_path)
    with _client_with_llm(tmp_path, FailingSummaryLlmClient()) as client:
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

        response = client.post(f"/api/excel/versions/{version_id}/summary/generate")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The model request failed. Please try again shortly."
    }


def test_document_summary_can_be_updated(
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

    summary_response = client.post(f"/api/excel/versions/{version_id}/summary/generate")
    assert summary_response.status_code == 200

    update_response = client.patch(
        f"/api/excel/versions/{version_id}/summary",
        json={
            "document_title": "Editable generated title",
            "summary_text": "Updated workbook summary.",
            "business_domain": "standards operations",
            "key_topics": ["Standards", "Standards", "DOW", ""],
            "suitable_questions": ["Which standards are listed?"],
            "routing_notes": "",
        },
    )
    assert update_response.status_code == 200
    updated_summary = update_response.json()
    assert updated_summary["document_title"] == "Editable generated title"
    assert updated_summary["summary_text"] == "Updated workbook summary."
    assert updated_summary["business_domain"] == "standards operations"
    assert updated_summary["key_topics"] == ["Standards", "DOW"]
    assert updated_summary["suitable_questions"] == ["Which standards are listed?"]
    assert updated_summary["routing_notes"] == ""

    persisted_response = client.get(f"/api/excel/versions/{version_id}/summary")
    assert persisted_response.status_code == 200
    assert persisted_response.json()["document_title"] == "Editable generated title"
    assert persisted_response.json()["key_topics"] == ["Standards", "DOW"]


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
        assert first_answer["citations"][0]["evidence_id"].endswith("::S001_R205")
        assert first_answer["citations"][0]["row_id"] == "S001_R205"
        assert len(llm_client.answer_calls[0]["rows"]) == 221

        history_response = client.get(f"/api/excel/chat/sessions/{session_id}/turns")
        assert history_response.status_code == 200
        turns = history_response.json()["turns"]
        assert len(turns) == 1
        assert turns[0]["question"] == "What standards are listed?"
        assert turns[0]["answer"]["answer_blocks"] == first_answer["answer_blocks"]
        assert turns[0]["answer"]["citations"] == first_answer["citations"]
        assert turns[0]["answer"]["selected_documents"] == first_answer["selected_documents"]

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

        persisted_history_response = client.get(f"/api/excel/chat/sessions/{session_id}/turns")
        assert persisted_history_response.status_code == 200
        persisted_turns = persisted_history_response.json()["turns"]
        assert [turn["question"] for turn in persisted_turns] == [
            "What standards are listed?",
            "What is the date for that?",
        ]
        assert persisted_turns[0]["answer"]["citations"][0]["row"] == (
            first_answer["citations"][0]["row"]
        )


def test_chat_session_can_be_listed_renamed_pinned_and_deleted(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(tmp_path, llm_client) as client:
        first_response = client.post("/api/excel/chat/sessions")
        second_response = client.post("/api/excel/chat/sessions")
        assert first_response.status_code == 200
        assert second_response.status_code == 200
        first_session_id = first_response.json()["session_id"]
        second_session_id = second_response.json()["session_id"]

        rename_response = client.patch(
            f"/api/excel/chat/sessions/{first_session_id}",
            json={"title": "Financial Analysis Q3"},
        )
        assert rename_response.status_code == 200
        renamed = rename_response.json()
        assert renamed["title"] == "Financial Analysis Q3"
        assert renamed["pinned_at"] is None

        pin_response = client.patch(
            f"/api/excel/chat/sessions/{first_session_id}/pin",
            json={"pinned": True},
        )
        assert pin_response.status_code == 200
        pinned = pin_response.json()
        assert pinned["pinned_at"] is not None

        list_response = client.get("/api/excel/chat/sessions")
        assert list_response.status_code == 200
        sessions = list_response.json()["sessions"]
        assert [session["session_id"] for session in sessions] == [
            first_session_id,
            second_session_id,
        ]

        unpin_response = client.patch(
            f"/api/excel/chat/sessions/{first_session_id}/pin",
            json={"pinned": False},
        )
        assert unpin_response.status_code == 200
        assert unpin_response.json()["pinned_at"] is None

        delete_response = client.delete(f"/api/excel/chat/sessions/{first_session_id}")
        assert delete_response.status_code == 204

        missing_response = client.get(f"/api/excel/chat/sessions/{first_session_id}")
        assert missing_response.status_code == 404


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


def test_chat_answer_request_passes_deep_thinking_flag(
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

        response = client.post(
            f"/api/excel/chat/sessions/{session_id}/messages",
            json={
                "question": "Think carefully about the standards.",
                "enable_deep_thinking": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["answer_blocks"][0]["reasoning"] == "Captured reasoning."
        assert llm_client.answer_calls[0]["enable_deep_thinking"] is True


def test_langgraph_workflow_runs_full_chat_chain(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(
        tmp_path,
        llm_client,
        workflow=LangGraphChatWorkflow(),
    ) as client:
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

        chat_response = client.post(
            "/api/excel/chat",
            json={"question": "What standards are listed?"},
        )

        assert chat_response.status_code == 200
        answer_payload = chat_response.json()
        assert llm_client.route_calls[0]["question"] == "What standards are listed?"
        assert llm_client.answer_calls[0]["question"] == "What standards are listed?"
        assert answer_payload["selected_documents"][0]["version_id"] == version_id
        assert {"route_total", "answer_total", "chat_total"}.issubset(
            {timing["stage"] for timing in answer_payload["timings"]}
        )


def test_llm_options_endpoint_and_request_level_models(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(tmp_path, llm_client) as client:
        options_response = client.get("/api/excel/llm/options")
        assert options_response.status_code == 200
        options_payload = options_response.json()
        assert "deepseek-ai/DeepSeek-V4-Pro" in options_payload["models"]
        assert "Qwen/Qwen3.6-27B" in options_payload["models"]
        assert options_payload["models"][0] == "inclusionAI/Ling-flash-2.0"
        providers_by_id = {
            provider["provider"]: provider
            for provider in options_payload["providers"]
        }
        assert providers_by_id["deepseek"]["deep_thinking_models"] == [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
        ]
        assert providers_by_id["siliconflow"]["deep_thinking_models"] == [
            "Pro/deepseek-ai/DeepSeek-V3.2",
        ]
        assert options_payload["defaults"] == {
            "summary_provider": "deepseek",
            "summary_model": "deepseek-v4-pro",
            "router_provider": "siliconflow",
            "router_model": "Qwen/Qwen3.6-35B-A3B",
            "answer_provider": "deepseek",
            "answer_model": "deepseek-v4-pro",
        }

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

        summary_response = client.post(
            f"/api/excel/versions/{version_id}/summary/generate",
            json={"model": "Qwen/Qwen3.6-27B"},
        )
        assert summary_response.status_code == 200

        session_id = client.post("/api/excel/chat/sessions").json()["session_id"]
        route_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/route",
            json={
                "question": "route first",
                "router_model": "inclusionAI/Ling-flash-2.0",
            },
        )
        assert route_response.status_code == 200
        selected_version_ids = [
            document["version_id"] for document in route_response.json()["selected_documents"]
        ]

        answer_response = client.post(
            f"/api/excel/chat/sessions/{session_id}/answer",
            json={
                "question": "route first",
                "answer_model": "deepseek-ai/DeepSeek-V4-Pro",
                "selected_version_ids": selected_version_ids,
            },
        )
        assert answer_response.status_code == 200

        assert llm_client.summary_models == ["Qwen/Qwen3.6-27B"]
        assert llm_client.route_models == ["inclusionAI/Ling-flash-2.0"]
        assert llm_client.answer_models == ["deepseek-ai/DeepSeek-V4-Pro"]


def test_llm_preferences_are_persisted(
    tmp_path: Path,
) -> None:
    llm_client = CapturingLlmClient()
    with _client_with_llm(tmp_path, llm_client) as client:
        default_response = client.get("/api/excel/llm/preferences")
        assert default_response.status_code == 200
        assert default_response.json()["summary_provider"] == "deepseek"

        save_response = client.patch(
            "/api/excel/llm/preferences",
            json={
                "summary_provider": "siliconflow",
                "summary_model": "Qwen/Qwen3.6-27B",
                "router_provider": "deepseek",
                "router_model": "deepseek-v4-flash",
                "answer_provider": "siliconflow",
                "answer_model": "deepseek-ai/DeepSeek-V4-Pro",
            },
        )
        assert save_response.status_code == 200
        saved = save_response.json()
        assert saved["scope"] == "workspace"
        assert saved["summary_model"] == "Qwen/Qwen3.6-27B"
        assert saved["updated_at"]

        persisted_response = client.get("/api/excel/llm/preferences")
        assert persisted_response.status_code == 200
        assert persisted_response.json() == saved


def test_verifier_uses_evidence_id_to_keep_correct_file() -> None:
    chat = ChatService(
        excel_assets=None,  # type: ignore[arg-type]
        summaries=None,  # type: ignore[arg-type]
        llm_client=FakeLlmClient(),
        sessions=None,  # type: ignore[arg-type]
    )
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        ),
        "version_b::sheet_b::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_b::sheet_b::S001_R5",
            file_id="file_b",
            version_id="version_b",
            sheet_id="sheet_b",
            sheet_name="Sheet B",
            row_id="S001_R5",
            row=["S001_R5", "B row"],
        ),
    }

    citations, evidence_id_to_citation_id, warnings = chat._build_verified_citations(
        [
            DraftCitation(
                evidence_id="version_a::sheet_a::S001_R5",
                quote="A row",
            )
        ],
        ["version_a::sheet_a::S001_R5"],
        citation_index,
    )

    assert warnings == []
    assert evidence_id_to_citation_id == {"version_a::sheet_a::S001_R5": "C1"}
    assert citations[0].file_id == "file_a"
    assert citations[0].sheet_id == "sheet_a"
    assert citations[0].row_id == "S001_R5"


def test_verifier_rejects_ambiguous_legacy_row_id() -> None:
    chat = ChatService(
        excel_assets=None,  # type: ignore[arg-type]
        summaries=None,  # type: ignore[arg-type]
        llm_client=FakeLlmClient(),
        sessions=None,  # type: ignore[arg-type]
    )
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        ),
        "version_b::sheet_b::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_b::sheet_b::S001_R5",
            file_id="file_b",
            version_id="version_b",
            sheet_id="sheet_b",
            sheet_name="Sheet B",
            row_id="S001_R5",
            row=["S001_R5", "B row"],
        ),
    }

    citations, evidence_id_to_citation_id, warnings = chat._build_verified_citations(
        [DraftCitation(row_id="S001_R5", quote="legacy row id only")],
        ["S001_R5"],
        citation_index,
    )

    assert citations == []
    assert evidence_id_to_citation_id == {}
    assert any("ignored ambiguous citation row_id: S001_R5" == warning for warning in warnings)


def test_verifier_rejects_invalid_evidence_id() -> None:
    chat = ChatService(
        excel_assets=None,  # type: ignore[arg-type]
        summaries=None,  # type: ignore[arg-type]
        llm_client=FakeLlmClient(),
        sessions=None,  # type: ignore[arg-type]
    )
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        )
    }

    citations, evidence_id_to_citation_id, warnings = chat._build_verified_citations(
        [DraftCitation(evidence_id="version_x::sheet_y::S001_R5", quote="bad")],
        ["version_x::sheet_y::S001_R5"],
        citation_index,
    )

    assert citations == []
    assert evidence_id_to_citation_id == {}
    assert any(
        warning == "ignored invalid citation evidence_id: version_x::sheet_y::S001_R5"
        for warning in warnings
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
        self.summary_models: list[str | None] = []
        self.route_models: list[str | None] = []
        self.answer_models: list[str | None] = []
        self.route_calls: list[dict] = []
        self.answer_calls: list[dict] = []

    def generate_document_summary(
        self,
        profile,
        *,
        model: str | None = None,
        provider: str | None = None,
    ):
        _ = provider
        self.summary_models.append(model)
        return super().generate_document_summary(profile, model=model, provider=provider)

    def route_documents(
        self,
        question: str,
        summaries: list[DocumentSummary],
        max_documents: int,
        user_questions: list[str] | None = None,
        attached_documents: list[AttachedDocument] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> list[SelectedDocument]:
        _ = provider
        self.route_models.append(model)
        self.route_calls.append(
            {
                "question": question,
                "user_questions": user_questions or [],
                "attached_documents": attached_documents or [],
                "previous_turns": previous_turns or [],
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
        model: str | None = None,
        provider: str | None = None,
        enable_deep_thinking: bool = False,
    ) -> DraftChatAnswer:
        _ = provider
        self.answer_models.append(model)
        self.answer_calls.append(
            {
                "question": question,
                "documents": documents,
                "rows": rows,
                "previous_turns": previous_turns or [],
                "enable_deep_thinking": enable_deep_thinking,
            }
        )
        available_row_ids = {str(row["row_id"]) for row in rows}
        row_id = "S001_R205" if "S001_R205" in available_row_ids else str(rows[-1]["row_id"])
        evidence_id = next(
            str(row["evidence_id"])
            for row in rows
            if str(row["row_id"]) == row_id
        )
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=f"Captured answer for {question}.",
                    evidence_ids=[evidence_id],
                    reasoning="Captured reasoning." if enable_deep_thinking else "",
                )
            ],
            citations=[DraftCitation(evidence_id=evidence_id, quote="captured row")],
            insufficient_evidence=False,
            follow_up_suggestions=[],
        )


@contextmanager
def _client_with_llm(
    tmp_path: Path,
    llm_client: FakeLlmClient,
    workflow: ChatWorkflow | None = None,
) -> Iterator[TestClient]:
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
        workflow=workflow,
    )
    app.dependency_overrides[get_excel_asset_service] = lambda: excel_assets
    app.dependency_overrides[get_document_summary_service] = lambda: summaries
    app.dependency_overrides[get_chat_service] = lambda: chat
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
