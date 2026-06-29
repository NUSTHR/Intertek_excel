from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.pdf import FakePdfParser
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.api.dependencies import (
    get_current_user,
    get_pdf_chat_service,
    get_pdf_knowledge_service,
    get_pdf_upload_task_worker,
    require_admin_user,
)
from app.application.llm_preferences import WorkspaceLlmPreferenceService
from app.application.pdf_knowledge import PdfKnowledgeService, PdfUploadTaskWorker
from app.application.pdf_knowledge.chat import PdfChatService
from app.application.pdf_knowledge.retrieval import PdfRetrievalService
from app.core.config import Settings
from app.domain.models import (
    AuthenticatedUser,
    PdfFileVisibility,
    PdfProcessingStatus,
    PdfUploadTaskStatus,
    UserRole,
)
from app.main import app
from app.ports.pdf_parser import ParsedPdfDocument, PdfParserRuntimeStatus
from tests.auth_helpers import admin_user, member_user


@pytest.fixture
def pdf_repository(tmp_path: Path) -> SQLiteExcelAssetRepository:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf.sqlite3")
    repository.initialize()
    return repository


@pytest.fixture
def client(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> Iterator[TestClient]:
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=FakePdfParser(),
        parser_status=PdfParserRuntimeStatus(
            backend="fake",
            available=True,
            detail="Fake parser for API tests.",
        ),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    chat_service = PdfChatService(
        retrieval=PdfRetrievalService(repository=pdf_repository),
        llm_client=FakeLlmClient(),
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: service
    app.dependency_overrides[get_pdf_upload_task_worker] = lambda: worker
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    app.dependency_overrides[get_current_user] = admin_user
    app.dependency_overrides[require_admin_user] = admin_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_pdf_upload_indexes_document_and_exposes_detail(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            (
                "files",
                (
                    "safety-standard.pdf",
                    _pdf_bytes(),
                    "application/pdf",
                ),
            )
        ],
    )

    assert response.status_code == 202
    task = response.json()["tasks"][0]
    assert task["status"] == "queued"
    assert task["stage"] == "queued"
    assert task["progress"] == 5
    assert task["parser_backend"] == "fake"
    assert task["retry_count"] == 0
    file_id = task["file_id"]
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    list_response = client.get("/api/pdf/files")
    assert list_response.status_code == 200
    files = list_response.json()["files"]
    assert files[0]["file_id"] == file_id
    assert files[0]["processing_status"] == "ready"
    assert files[0]["page_count"] >= 1
    assert files[0]["chunk_count"] >= 1

    task_response = client.get(f"/api/pdf/files/upload-tasks/{task['task_id']}")
    assert task_response.status_code == 200
    completed_task = task_response.json()
    assert completed_task["status"] == "ready"
    assert completed_task["stage"] == "ready"
    assert completed_task["error_code"] is None

    detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["file_id"] == file_id
    assert detail["preview_blocks"]
    assert detail["schema"]
    assert "#pdf" in detail["tags"]

    chunks_response = client.get(f"/api/pdf/files/{file_id}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()["chunks"]
    assert chunks
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["text"]
    assert chunks[0]["token_count"] >= 1
    assert len(chunks[0]["content_hash"]) == 64


def test_pdf_parser_status_is_exposed(client: TestClient) -> None:
    response = client.get("/api/pdf/parser/status")

    assert response.status_code == 200
    status = response.json()
    assert status == {
        "backend": "fake",
        "available": True,
        "command": None,
        "version": None,
        "detail": "Fake parser for API tests.",
    }


def test_pdf_folder_upload_preserves_supported_file_hierarchy(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            (
                "files",
                (
                    "Project Alpha/Financials/safety-standard.pdf",
                    _pdf_bytes(),
                    "application/pdf",
                ),
            ),
            ("files", ("Project Alpha/README.md", b"skip me", "text/markdown")),
        ],
    )

    assert response.status_code == 202
    assert len(response.json()["tasks"]) == 1
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    list_response = client.get("/api/pdf/files")
    assert list_response.status_code == 200
    files = list_response.json()["files"]
    root_folder = next(file for file in files if file["display_name"] == "Project Alpha")
    child_folder = next(file for file in files if file["display_name"] == "Financials")
    document = next(file for file in files if file["display_name"] == "safety-standard.pdf")

    assert root_folder["kind"] == "folder"
    assert child_folder["parent_id"] == root_folder["file_id"]
    assert document["parent_id"] == child_folder["file_id"]


def test_pdf_summary_generation_persists_ready_summary(client: TestClient) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    summary_response = client.post(f"/api/pdf/files/{file_id}/summary/generate")
    assert summary_response.status_code == 200
    summary = summary_response.json()["summary"]
    assert summary["status"] == "ready"
    assert "indexed and ready" in summary["content"]

    detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
    assert detail_response.status_code == 200
    assert detail_response.json()["summary"]["content"] == summary["content"]


def test_pdf_chunk_search_returns_ranked_matches(client: TestClient) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    search_response = client.post(
        "/api/pdf/retrieval/search",
        json={"query": "compliance evidence", "file_ids": [file_id], "limit": 5},
    )

    assert search_response.status_code == 200
    result = search_response.json()
    assert result["query"] == "compliance evidence"
    assert result["total_matches"] >= 1
    assert result["limit"] == 5
    match = result["matches"][0]
    assert match["file"]["file_id"] == file_id
    assert match["chunk"]["text"]
    assert match["score"] > 0
    assert "compliance" in match["matched_terms"]
    assert match["excerpt"]


def test_pdf_chunk_search_can_scan_visible_ready_documents(client: TestClient) -> None:
    first_file_id = _upload_pdf(client, filename="safety-standard.pdf")
    second_file_id = _upload_pdf(client, filename="evidence-guide.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True

    search_response = client.post(
        "/api/pdf/retrieval/search",
        json={"query": "Knowledge Index", "limit": 10},
    )

    assert search_response.status_code == 200
    file_ids = {
        match["file"]["file_id"]
        for match in search_response.json()["matches"]
    }
    assert {first_file_id, second_file_id}.issubset(file_ids)


def test_pdf_chat_answers_with_citations(client: TestClient) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    chat_response = client.post(
        "/api/pdf/chat",
        json={
            "question": "What does the PDF say about compliance evidence?",
            "file_ids": [file_id],
            "retrieval_limit": 5,
        },
    )

    assert chat_response.status_code == 200
    answer = chat_response.json()
    assert answer["question"] == "What does the PDF say about compliance evidence?"
    assert answer["answer_blocks"]
    assert "Draft PDF answer" in answer["answer_blocks"][0]["text"]
    assert answer["citations"]
    assert answer["citations"][0]["citation_id"] == "P1"
    assert answer["citations"][0]["file_id"] == file_id
    assert answer["retrieval_matches"]
    assert answer["insufficient_evidence"] is False


def test_pdf_model_settings_can_be_listed_and_updated(client: TestClient) -> None:
    list_response = client.get("/api/pdf/model-settings")
    assert list_response.status_code == 200
    settings = list_response.json()["settings"]
    assert [setting["id"] for setting in settings] == ["summary", "router", "chat"]

    patch_response = client.patch(
        "/api/pdf/model-settings/summary",
        json={
            "selected_provider": "DeepSeek",
            "selected_model": "gpt-4o",
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["settings"][0]
    assert updated["id"] == "summary"
    assert updated["selected_provider"] == "DeepSeek"
    assert updated["selected_model"] == "gpt-4o"


def test_pdf_upload_rejects_empty_and_unsupported_files(client: TestClient) -> None:
    empty_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("empty.pdf", b"", "application/pdf"))],
    )
    assert empty_response.status_code == 400
    assert "empty" in empty_response.json()["detail"]

    unsupported_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert unsupported_response.status_code == 400
    assert "supported" in unsupported_response.json()["detail"]

    search_response = client.post(
        "/api/pdf/retrieval/search",
        json={"query": "   ", "limit": 5},
    )
    assert search_response.status_code == 400
    assert "query" in search_response.json()["detail"]


def test_member_cannot_see_hidden_pdf_file(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    file = pdf_repository.get_pdf_file(file_id)
    assert file is not None
    pdf_repository.update_pdf_file_visibility(
        file_id=file_id,
        visibility=PdfFileVisibility.HIDDEN,
        updated_at=file.updated_at,
    )

    app.dependency_overrides[get_current_user] = member_user
    try:
        list_response = client.get("/api/pdf/files")
        detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
        chunks_response = client.get(f"/api/pdf/files/{file_id}/chunks")
        search_response = client.post(
            "/api/pdf/retrieval/search",
            json={"query": "compliance", "file_ids": [file_id], "limit": 5},
        )
        chat_response = client.post(
            "/api/pdf/chat",
            json={"question": "compliance", "file_ids": [file_id]},
        )
    finally:
        app.dependency_overrides[get_current_user] = admin_user

    assert list_response.status_code == 200
    assert list_response.json()["files"] == []
    assert detail_response.status_code == 404
    assert chunks_response.status_code == 404
    assert search_response.status_code == 404
    assert chat_response.status_code == 404


def test_pdf_upload_task_requires_owner(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("owner-check.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 202
    task_id = response.json()["tasks"][0]["task_id"]

    app.dependency_overrides[require_admin_user] = lambda: AuthenticatedUser(
        user_id="other_admin_test",
        email="other-admin@example.com",
        role=UserRole.ADMIN,
        created_at="2026-01-01T00:00:00+00:00",
    )
    try:
        forbidden_response = client.get(f"/api/pdf/files/upload-tasks/{task_id}")
    finally:
        app.dependency_overrides[require_admin_user] = admin_user

    assert forbidden_response.status_code == 404


def test_pdf_worker_records_parser_failure(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=FailingPdfParser(),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    task = service.create_upload_task(
        user_id=admin_user().user_id,
        original_filename="broken.pdf",
        content=_pdf_bytes(),
    )

    assert worker.run_once() is True

    failed_task = pdf_repository.get_pdf_upload_task(task.task_id)
    failed_file = pdf_repository.get_pdf_file(str(task.file_id))
    assert failed_task is not None
    assert failed_task.status == PdfUploadTaskStatus.FAILED
    assert failed_task.stage.value == "failed"
    assert failed_task.error_code == "parser_failed"
    assert failed_task.parser_backend == "FailingPdfParser"
    assert "parser exploded" in str(failed_task.error_message)
    assert failed_file is not None
    assert failed_file.processing_status == PdfProcessingStatus.FAILED


def test_pdf_worker_marks_stale_processing_task_with_diagnostics(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("stale.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 202
    task_id = response.json()["tasks"][0]["task_id"]
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    claimed = pdf_repository.claim_next_pdf_upload_task(
        worker_id="stale-test-worker",
        started_at="2020-01-01T00:00:00+00:00",
    )
    assert claimed is not None

    failed_count = worker.mark_stale_processing_tasks_failed(max_processing_age_minutes=1)

    assert failed_count == 1
    failed_task = pdf_repository.get_pdf_upload_task(task_id)
    assert failed_task is not None
    assert failed_task.status == PdfUploadTaskStatus.FAILED
    assert failed_task.stage.value == "failed"
    assert failed_task.error_code == "stale_processing_task"


def _upload_pdf(client: TestClient, filename: str = "safety-standard.pdf") -> str:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", (filename, _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 202
    return str(response.json()["tasks"][0]["file_id"])


class FailingPdfParser:
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        raise RuntimeError("parser exploded")


def _pdf_bytes() -> bytes:
    return (
        b"%PDF-1.7\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Count 2 /Kids [3 0 R 4 0 R] >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"4 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"Safety requirements, compliance clauses, and test evidence.\n"
        b"%%EOF"
    )
