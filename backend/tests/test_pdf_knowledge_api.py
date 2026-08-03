from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Match

from app.adapters.llm.fake_llm_client import FakeLlmClient
from app.adapters.pdf import FakePdfParser
from app.adapters.repositories.sqlite_repository import SQLiteExcelAssetRepository
from app.adapters.storage.filesystem_storage import FilesystemExcelArtifactStorage
from app.adapters.workbook.openpyxl_reader import OpenpyxlWorkbookReader
from app.api.dependencies import (
    get_chat_cancellation_registry,
    get_chat_service,
    get_current_user,
    get_document_summary_service,
    get_excel_asset_service,
    get_pdf_chat_service,
    get_pdf_knowledge_service,
    get_pdf_summary_task_worker,
    get_pdf_upload_task_worker,
    require_admin_user,
)
from app.application.chat.cancellation import ChatCancellationRegistry
from app.application.chat.service import ChatService
from app.application.document_summaries.service import DocumentSummaryService
from app.application.excel_assets.service import ExcelAssetService
from app.application.llm_preferences import WorkspaceLlmPreferenceService
from app.application.pdf_knowledge import (
    PdfKnowledgeService,
    PdfSummaryTaskWorker,
    PdfUploadTaskWorker,
)
from app.application.pdf_knowledge.chat import PdfChatService
from app.core.config import Settings
from app.core.errors import AuthorizationError, LlmRequestError, PdfRoutingError
from app.core.llm_catalog import (
    DEFAULT_ANSWER_MODEL,
    DEFAULT_ANSWER_PROVIDER,
    DEFAULT_ROUTER_MODEL,
    DEFAULT_ROUTER_PROVIDER,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_SUMMARY_PROVIDER,
    SILICONFLOW_PROVIDER,
    list_supported_llm_models,
    list_supported_llm_provider_options,
)
from app.domain.models import (
    AuthenticatedUser,
    PdfFileVisibility,
    PdfModelSetting,
    PdfParsePageStatus,
    PdfParseQualityStatus,
    PdfProcessingStatus,
    PdfUploadTaskStatus,
    SelectedDocument,
    UserRole,
)
from app.main import app
from app.ports.pdf_parser import (
    ParsedPdfArtifact,
    ParsedPdfChunk,
    ParsedPdfDocument,
    ParsedPdfPage,
    PdfParserProfile,
    PdfParserRuntimeStatus,
)
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
        llm_client=FakeLlmClient(),
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    summary_worker = PdfSummaryTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        poll_interval_seconds=0.1,
    )
    chat_service = PdfChatService(
        llm_client=FakeLlmClient(),
        sessions=pdf_repository,
    )
    excel_assets = ExcelAssetService(
        repository=pdf_repository,
        storage=FilesystemExcelArtifactStorage(tmp_path / "storage"),
        workbook_reader=OpenpyxlWorkbookReader(),
    )
    summaries = DocumentSummaryService(
        excel_assets=excel_assets,
        llm_client=FakeLlmClient(),
        repository=pdf_repository,
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    excel_chat_service = ChatService(
        excel_assets=excel_assets,
        summaries=summaries,
        llm_client=FakeLlmClient(),
        sessions=pdf_repository,
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: service
    app.dependency_overrides[get_pdf_upload_task_worker] = lambda: worker
    app.dependency_overrides[get_pdf_summary_task_worker] = lambda: summary_worker
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    app.dependency_overrides[get_chat_cancellation_registry] = lambda: (
        ChatCancellationRegistry(repository=pdf_repository)
    )
    app.dependency_overrides[get_excel_asset_service] = lambda: excel_assets
    app.dependency_overrides[get_document_summary_service] = lambda: summaries
    app.dependency_overrides[get_chat_service] = lambda: excel_chat_service
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
    assert files[0]["quality_status"] == "good"
    assert files[0]["coverage_ratio"] > 0
    assert files[0]["warning_count"] == 0
    assert files[0]["failed_page_count"] == 0
    assert files[0]["parser_backend"] == "fake"

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
    assert detail["parse_report"]["quality_status"] == "good"
    assert detail["parse_report"]["coverage_ratio"] > 0
    assert detail["parse_report"]["pages"]

    chunks_response = client.get(f"/api/pdf/files/{file_id}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()["chunks"]
    assert chunks
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["text"]
    assert chunks[0]["token_count"] >= 1
    assert len(chunks[0]["content_hash"]) == 64


def test_pdf_upload_collection_routes_are_not_shadowed(client: TestClient) -> None:
    tasks_response = client.get("/api/pdf/files/upload-tasks")
    batches_response = client.get("/api/pdf/files/upload-batches")

    assert tasks_response.status_code == 200
    assert tasks_response.json() == {"tasks": []}
    assert batches_response.status_code == 200
    assert batches_response.json() == {"batches": []}


def test_static_http_routes_are_not_shadowed_by_dynamic_routes() -> None:
    routes = list(app.routes)
    for expected_route in routes:
        path = getattr(expected_route, "path", "")
        methods = getattr(expected_route, "methods", set()) or set()
        if not path or "{" in path:
            continue
        for method in methods:
            scope = {
                "type": "http",
                "path": path,
                "root_path": "",
                "method": method,
                "scheme": "http",
                "query_string": b"",
                "headers": [],
                "server": ("test", 80),
                "client": ("test", 1),
                "http_version": "1.1",
            }
            matched_route = next(
                route
                for route in routes
                if route.matches(scope)[0] == Match.FULL
            )
            assert matched_route is expected_route, (
                f"{method} {path} is shadowed by "
                f"{getattr(matched_route, 'path', '<unknown>')}"
            )


def test_pdf_folder_upload_creates_batch_and_preserves_hierarchy(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/standard-a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/b/standard-b.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["batch"]["source_name"] == "root"
    assert payload["batch"]["accepted_files"] == 2
    assert len(payload["tasks"]) == 2
    assert {task["batch_id"] for task in payload["tasks"]} == {payload["batch"]["batch_id"]}

    batch_response = client.get(
        f"/api/pdf/files/upload-batches/{payload['batch']['batch_id']}"
    )
    assert batch_response.status_code == 200
    assert len(batch_response.json()["tasks"]) == 2

    files_response = client.get("/api/pdf/files")
    assert files_response.status_code == 200
    files = files_response.json()["files"]
    folders = {file["display_name"] for file in files if file["kind"] == "folder"}
    assert {"root", "a", "b"}.issubset(folders)


def test_pdf_upload_places_single_file_in_selected_folder(client: TestClient) -> None:
    _upload_pdf(client, filename="target/seed.pdf")
    files = client.get("/api/pdf/files").json()["files"]
    target_folder = _find_pdf_file(files, name="target", kind="folder")

    response = client.post(
        "/api/pdf/files/upload-tasks",
        data={"parent_id": target_folder["file_id"]},
        files=[
            ("files", ("test.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )

    assert response.status_code == 202
    uploaded_file_id = response.json()["tasks"][0]["file_id"]
    uploaded_files = client.get("/api/pdf/files").json()["files"]
    uploaded_file = next(
        file for file in uploaded_files if file["file_id"] == uploaded_file_id
    )
    assert uploaded_file["display_name"] == "test.pdf"
    assert uploaded_file["parent_id"] == target_folder["file_id"]


def test_pdf_folder_upload_is_nested_under_selected_folder(client: TestClient) -> None:
    _upload_pdf(client, filename="target/seed.pdf")
    files = client.get("/api/pdf/files").json()["files"]
    target_folder = _find_pdf_file(files, name="target", kind="folder")

    response = client.post(
        "/api/pdf/files/upload-tasks",
        data={"parent_id": target_folder["file_id"]},
        files=[
            ("files", ("test_pdf/test.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )

    assert response.status_code == 202
    uploaded_files = client.get("/api/pdf/files").json()["files"]
    nested_folder = next(
        file
        for file in uploaded_files
        if file["display_name"] == "test_pdf"
        and file["kind"] == "folder"
        and file["parent_id"] == target_folder["file_id"]
    )
    uploaded_file_id = response.json()["tasks"][0]["file_id"]
    uploaded_file = next(
        file for file in uploaded_files if file["file_id"] == uploaded_file_id
    )
    assert uploaded_file["parent_id"] == nested_folder["file_id"]


def test_pdf_upload_rejects_non_folder_target(client: TestClient) -> None:
    file_id = _upload_pdf(client, filename="not-a-folder.pdf")

    response = client.post(
        "/api/pdf/files/upload-tasks",
        data={"parent_id": file_id},
        files=[
            ("files", ("test.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "target PDF folder was not found"


def test_pdf_folder_upload_reuses_existing_folder_nodes(client: TestClient) -> None:
    first_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/standard-a.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert first_response.status_code == 202

    second_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/standard-b.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert second_response.status_code == 202

    files_response = client.get("/api/pdf/files")
    assert files_response.status_code == 200
    files = files_response.json()["files"]
    root_folders = [
        file for file in files if file["kind"] == "folder" and file["display_name"] == "root"
    ]
    assert len(root_folders) == 1
    child_folders = [
        file
        for file in files
        if file["kind"] == "folder"
        and file["display_name"] == "a"
        and file["parent_id"] == root_folders[0]["file_id"]
    ]
    assert len(child_folders) == 1


def test_pdf_file_can_be_renamed_hidden_and_deleted_from_directory(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="root/a/safety-standard.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    rename_response = client.patch(
        f"/api/pdf/files/{file_id}",
        json={"display_name": "renamed-standard.pdf"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["display_name"] == "renamed-standard.pdf"

    hidden_response = client.patch(
        f"/api/pdf/files/{file_id}/visibility",
        json={"visible_to_members": False},
    )
    assert hidden_response.status_code == 200
    assert hidden_response.json()["visible_to_members"] is False

    app.dependency_overrides[get_current_user] = member_user
    try:
        member_list = client.get("/api/pdf/files")
    finally:
        app.dependency_overrides[get_current_user] = admin_user
    assert member_list.status_code == 200
    assert file_id not in {file["file_id"] for file in member_list.json()["files"]}

    delete_confirmation = client.delete(f"/api/pdf/files/{file_id}")
    assert delete_confirmation.status_code == 409
    assert delete_confirmation.json()["requires_confirmation"] is True

    delete_response = client.delete(f"/api/pdf/files/{file_id}?confirm_delete=true")
    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["file_id"] == file_id
    assert deleted["deleted_files"] == 1
    assert deleted["deleted_chunks"] == 0

    assert client.get(f"/api/pdf/files/{file_id}/detail").status_code == 404
    assert client.get("/api/pdf/files").json()["files"][0]["kind"] == "folder"
    assert pdf_repository.get_pdf_document_detail(file_id) is not None
    assert pdf_repository.list_pdf_document_chunks(file_id)


def test_pdf_file_rename_conflict_is_scoped_to_parent(client: TestClient) -> None:
    first_id = _upload_pdf(client, filename="root/a/alpha.pdf")
    second_id = _upload_pdf(client, filename="root/a/beta.pdf")
    third_id = _upload_pdf(client, filename="root/b/beta.pdf")

    conflict_response = client.patch(
        f"/api/pdf/files/{first_id}",
        json={"display_name": "beta.pdf"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["requires_confirmation"] is True

    allowed_response = client.patch(
        f"/api/pdf/files/{third_id}",
        json={"display_name": "alpha.pdf"},
    )
    assert allowed_response.status_code == 200
    assert allowed_response.json()["display_name"] == "alpha.pdf"

    unchanged_response = client.get(f"/api/pdf/files/{second_id}/detail")
    assert unchanged_response.status_code == 200


def test_pdf_folder_delete_hides_descendants_from_directory(
    client: TestClient,
) -> None:
    _upload_pdf(client, filename="root/a/safety-standard.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    files = client.get("/api/pdf/files").json()["files"]
    root_folder = _find_pdf_file(files, name="root", kind="folder")

    delete_response = client.delete(
        f"/api/pdf/files/{root_folder['file_id']}?confirm_delete=true"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_files"] == 3

    list_response = client.get("/api/pdf/files")
    assert list_response.status_code == 200
    assert list_response.json()["files"] == []


def test_pdf_repository_get_or_create_folder_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "pdf.sqlite3"
    first_repository = SQLiteExcelAssetRepository(database_path)
    first_repository.initialize()
    second_repository = SQLiteExcelAssetRepository(database_path)
    second_repository.initialize()

    first_folder = first_repository.get_or_create_pdf_folder(
        user_id=admin_user().user_id,
        parent_id=None,
        display_name="root",
        created_at="2026-06-30T00:00:00+00:00",
    )
    second_folder = second_repository.get_or_create_pdf_folder(
        user_id=admin_user().user_id,
        parent_id=None,
        display_name="root",
        created_at="2026-06-30T00:00:01+00:00",
    )

    assert second_folder.file_id == first_folder.file_id
    folders = [
        file
        for file in first_repository.list_pdf_files()
        if file.kind.value == "folder" and file.display_name == "root"
    ]
    assert len(folders) == 1
    assert folders[0].created_at == "2026-06-30T00:00:00+00:00"


def test_pdf_repository_folder_identity_is_scoped_by_parent(tmp_path: Path) -> None:
    repository = SQLiteExcelAssetRepository(tmp_path / "pdf.sqlite3")
    repository.initialize()
    user_id = admin_user().user_id

    root_a = repository.get_or_create_pdf_folder(
        user_id=user_id,
        parent_id=None,
        display_name="root-a",
        created_at="2026-07-01T00:00:00+00:00",
    )
    root_b = repository.get_or_create_pdf_folder(
        user_id=user_id,
        parent_id=None,
        display_name="root-b",
        created_at="2026-07-01T00:00:01+00:00",
    )
    first_child = repository.get_or_create_pdf_folder(
        user_id=user_id,
        parent_id=root_a.file_id,
        display_name="shared",
        created_at="2026-07-01T00:00:02+00:00",
    )
    same_child = repository.get_or_create_pdf_folder(
        user_id=user_id,
        parent_id=root_a.file_id,
        display_name="shared",
        created_at="2026-07-01T00:00:03+00:00",
    )
    sibling_child = repository.get_or_create_pdf_folder(
        user_id=user_id,
        parent_id=root_b.file_id,
        display_name="shared",
        created_at="2026-07-01T00:00:04+00:00",
    )

    assert same_child.file_id == first_child.file_id
    assert sibling_child.file_id != first_child.file_id
    assert same_child.parent_id == root_a.file_id
    assert sibling_child.parent_id == root_b.file_id

    shared_folders = [
        file
        for file in repository.list_pdf_files()
        if file.kind.value == "folder" and file.display_name == "shared"
    ]
    assert {folder.parent_id for folder in shared_folders} == {
        root_a.file_id,
        root_b.file_id,
    }


def test_pdf_upload_batch_reports_processing_after_partial_progress(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/standard-a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/b/standard-b.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert response.status_code == 202
    batch_id = response.json()["batch"]["batch_id"]
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()

    assert worker.run_once() is True

    batch_response = client.get(f"/api/pdf/files/upload-batches/{batch_id}")
    assert batch_response.status_code == 200
    batch = batch_response.json()["batch"]
    assert batch["status"] == "processing"
    assert batch["result"]["ready"] == 1
    assert batch["result"]["active"] == 1
    assert batch["detail"] == "1 of 2 documents parsed; 1 still active."


def test_pdf_upload_batch_records_skipped_file_reasons(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/valid.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/readme.txt", b"notes", "text/plain")),
            (
                "files",
                (
                    "root/workbook.xlsx",
                    b"not a pdf workbook",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
            ("files", ("root/empty.pdf", b"", "application/pdf")),
            ("files", ("root/oversize.pdf", b"x" * (51 * 1024 * 1024), "application/pdf")),
        ],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["batch"]["accepted_files"] == 1
    assert payload["batch"]["skipped_files"] == 4
    assert payload["batch"]["detail"] == "Queued 1 document; skipped 4 files."
    skipped = payload["batch"]["result"]["skipped_files_detail"]
    assert [item["filename"] for item in skipped] == [
        "readme.txt",
        "workbook.xlsx",
        "empty.pdf",
        "oversize.pdf",
    ]
    assert [item["reason"] for item in skipped] == [
        "unsupported PDF knowledge file type",
        "unsupported PDF knowledge file type",
        "uploaded file is empty",
        "uploaded file exceeds the 50 MB limit",
    ]
    assert skipped[0]["relative_path"] == "root/readme.txt"
    assert skipped[0]["size_bytes"] == 5
    assert len(payload["tasks"]) == 1


def test_pdf_queued_upload_task_can_be_cancelled(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("queued.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task = response.json()["tasks"][0]

    cancel_response = client.post(f"/api/pdf/files/upload-tasks/{task['task_id']}/cancel")

    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["stage"] == "cancelled"

    batch_response = client.get(f"/api/pdf/files/upload-batches/{task['batch_id']}")
    assert batch_response.status_code == 200
    assert batch_response.json()["batch"]["status"] == "cancelled"


def test_pdf_failed_upload_task_can_be_retried(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("retry.pdf", _pdf_bytes(), "application/pdf"))],
    )
    task = response.json()["tasks"][0]
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    # The default fake parser succeeds, so force a retryable state through the service.
    service = app.dependency_overrides[get_pdf_knowledge_service]()
    original_task = service.get_upload_task(task["task_id"], user_id=admin_user().user_id)
    service.fail_task(original_task, "forced retry test failure", error_code="forced_failure")

    retry_response = client.post(f"/api/pdf/files/upload-tasks/{task['task_id']}/retry")

    assert retry_response.status_code == 202
    retry_task = retry_response.json()
    assert retry_task["status"] == "queued"
    assert retry_task["retry_count"] == 1
    assert retry_task["batch_id"] == task["batch_id"]


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


def test_pdf_parser_diagnostics_require_admin_access(client: TestClient) -> None:
    def deny_admin_access() -> AuthenticatedUser:
        raise AuthorizationError("administrator access is required")

    app.dependency_overrides[require_admin_user] = deny_admin_access
    try:
        status_response = client.get("/api/pdf/parser/status")
        profiles_response = client.get("/api/pdf/parser/profiles")
    finally:
        app.dependency_overrides[require_admin_user] = admin_user

    assert status_response.status_code == 403
    assert profiles_response.status_code == 403


def test_pdf_parser_profiles_can_be_selected(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    local_status = PdfParserRuntimeStatus(
        backend="mineru-local",
        available=True,
        detail="Local parser.",
    )
    cloud_status = PdfParserRuntimeStatus(
        backend="mineru-cloud",
        available=True,
        detail="Cloud parser.",
    )
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=FakePdfParser(),
        parser_status=local_status,
        parser_profiles={
            "mineru-local": FakePdfParser(),
            "mineru-cloud": FakePdfParser(),
        },
        parser_profile_statuses={
            "mineru-local": local_status,
            "mineru-cloud": cloud_status,
        },
        parser_profile_descriptors=[
            PdfParserProfile(
                profile_id="mineru-local",
                label="Local MinerU",
                kind="local",
                status=local_status,
                is_default=True,
            ),
            PdfParserProfile(
                profile_id="mineru-cloud",
                label="MinerU Cloud",
                kind="cloud",
                status=cloud_status,
            ),
        ],
        default_parser_profile_id="mineru-local",
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: service
    app.dependency_overrides[get_current_user] = admin_user
    app.dependency_overrides[require_admin_user] = admin_user
    try:
        with TestClient(app) as test_client:
            profile_response = test_client.get("/api/pdf/parser/profiles")
            assert profile_response.status_code == 200
            assert profile_response.json()["selected_profile_id"] == "mineru-local"

            select_response = test_client.patch(
                "/api/pdf/parser/profiles",
                json={"selected_profile_id": "mineru-cloud"},
            )
            assert select_response.status_code == 200
            assert select_response.json()["selected_profile_id"] == "mineru-cloud"

            task = service.create_upload_task(
                user_id=admin_user().user_id,
                original_filename="cloud.pdf",
                content=_pdf_bytes(),
            )
            assert task.parser_backend == "mineru-cloud"
    finally:
        app.dependency_overrides.clear()


def test_pdf_parser_profile_selection_rejects_unavailable_profile(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    local_status = PdfParserRuntimeStatus(
        backend="mineru-local",
        available=True,
        detail="Local parser.",
    )
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=FakePdfParser(),
        parser_status=local_status,
        parser_profiles={
            "mineru-local": FakePdfParser(),
            "mineru-cloud": FakePdfParser(),
        },
        parser_profile_statuses={
            "mineru-local": local_status,
            "mineru-cloud": PdfParserRuntimeStatus(
                backend="mineru-cloud",
                available=False,
                detail="Token missing.",
            ),
        },
        default_parser_profile_id="mineru-local",
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: service
    app.dependency_overrides[get_current_user] = admin_user
    app.dependency_overrides[require_admin_user] = admin_user
    try:
        with TestClient(app) as test_client:
            response = test_client.patch(
                "/api/pdf/parser/profiles",
                json={"selected_profile_id": "mineru-cloud"},
            )
            assert response.status_code == 400
            assert "unavailable" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


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


def test_pdf_folder_upload_processes_complete_batch_with_parse_reports(
    client: TestClient,
) -> None:
    upload_paths = [
        "test_pdf/1/1.1/compliance-list-copy.pdf",
        "test_pdf/1/sample-copy-3.pdf",
        "test_pdf/sample.pdf",
        "test_pdf/3/3.1/compliance-list.pdf",
        "test_pdf/3/sample-copy-6.pdf",
        "test_pdf/2/sample-copy-4.pdf",
    ]

    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", (path, _pdf_bytes(), "application/pdf"))
            for path in upload_paths
        ],
    )

    assert response.status_code == 202
    payload = response.json()
    batch_id = payload["batch"]["batch_id"]
    assert payload["batch"]["source_name"] == "test_pdf"
    assert payload["batch"]["total_files"] == 6
    assert payload["batch"]["accepted_files"] == 6
    assert payload["batch"]["skipped_files"] == 0
    assert len(payload["tasks"]) == 6

    batch_detail = _drain_pdf_upload_batch(client, batch_id)

    assert batch_detail["batch"]["status"] == "ready"
    assert batch_detail["batch"]["progress"] == 100
    assert batch_detail["batch"]["detail"] == "All 6 documents parsed."
    assert batch_detail["batch"]["result"]["ready"] == 6
    assert batch_detail["batch"]["result"]["active"] == 0
    assert all(task["status"] == "ready" for task in batch_detail["tasks"])
    assert all(task["stage"] == "ready" for task in batch_detail["tasks"])
    assert all(task["result"]["quality_status"] == "good" for task in batch_detail["tasks"])

    files_response = client.get("/api/pdf/files")
    assert files_response.status_code == 200
    files = files_response.json()["files"]
    root_folder = _find_pdf_file(files, name="test_pdf", kind="folder")
    folder_1 = _find_pdf_file(files, name="1", kind="folder", parent_id=root_folder["file_id"])
    folder_1_1 = _find_pdf_file(files, name="1.1", kind="folder", parent_id=folder_1["file_id"])
    folder_2 = _find_pdf_file(files, name="2", kind="folder", parent_id=root_folder["file_id"])
    folder_3 = _find_pdf_file(files, name="3", kind="folder", parent_id=root_folder["file_id"])
    folder_3_1 = _find_pdf_file(files, name="3.1", kind="folder", parent_id=folder_3["file_id"])

    expected_parent_by_name = {
        "compliance-list-copy.pdf": folder_1_1["file_id"],
        "sample-copy-3.pdf": folder_1["file_id"],
        "sample.pdf": root_folder["file_id"],
        "compliance-list.pdf": folder_3_1["file_id"],
        "sample-copy-6.pdf": folder_3["file_id"],
        "sample-copy-4.pdf": folder_2["file_id"],
    }
    pdf_files = [file for file in files if file["kind"] == "pdf"]
    assert {file["display_name"] for file in pdf_files} == set(expected_parent_by_name)

    for file in pdf_files:
        assert file["parent_id"] == expected_parent_by_name[file["display_name"]]
        assert file["processing_status"] == "ready"
        assert file["quality_status"] == "good"
        assert file["coverage_ratio"] > 0
        assert file["warning_count"] == 0
        assert file["failed_page_count"] == 0
        assert file["parser_backend"] == "fake"

        detail_response = client.get(f"/api/pdf/files/{file['file_id']}/detail")
        assert detail_response.status_code == 200
        parse_report = detail_response.json()["parse_report"]
        assert parse_report["quality_status"] == file["quality_status"]
        assert parse_report["coverage_ratio"] == file["coverage_ratio"]
        assert parse_report["warning_count"] == file["warning_count"]
        assert parse_report["failed_pages"] == file["failed_page_count"]
        assert parse_report["parser_backend"] == file["parser_backend"]
        assert parse_report["pages"]

        chunks_response = client.get(f"/api/pdf/files/{file['file_id']}/chunks")
        assert chunks_response.status_code == 200
        assert chunks_response.json()["chunks"]


def test_pdf_summary_generation_persists_ready_summary(client: TestClient) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    summary_response = client.post(f"/api/pdf/files/{file_id}/summary/generate")
    assert summary_response.status_code == 200
    summary = summary_response.json()["summary"]
    assert summary["status"] == "ready"
    assert summary["document_title"] == "safety-standard.pdf"
    assert "safety-standard.pdf" in summary["content"]
    assert summary["key_topics"]

    detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
    assert detail_response.status_code == 200
    assert detail_response.json()["summary"]["content"] == summary["content"]

    rename_response = client.patch(
        f"/api/pdf/files/{file_id}",
        json={"display_name": "renamed-standard.pdf"},
    )
    assert rename_response.status_code == 200
    renamed_detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
    assert renamed_detail_response.status_code == 200
    assert (
        renamed_detail_response.json()["summary"]["document_title"]
        == "renamed-standard.pdf"
    )


def test_pdf_summary_tasks_queue_ready_documents_and_worker_generates_summaries(
    client: TestClient,
) -> None:
    first_file_id = _upload_pdf(client, filename="root/a/safety-standard-a.pdf")
    second_file_id = _upload_pdf(client, filename="root/b/safety-standard-b.pdf")
    upload_worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert upload_worker.run_once() is True
    assert upload_worker.run_once() is True

    create_response = client.post(
        "/api/pdf/summary-tasks",
        json={"file_ids": [first_file_id, second_file_id]},
    )

    assert create_response.status_code == 202
    tasks = create_response.json()["tasks"]
    assert [task["status"] for task in tasks] == ["queued", "queued"]
    assert {task["file_id"] for task in tasks} == {first_file_id, second_file_id}

    summary_worker = app.dependency_overrides[get_pdf_summary_task_worker]()
    assert summary_worker.run_once() is True
    assert summary_worker.run_once() is True
    assert summary_worker.run_once() is False

    list_response = client.get("/api/pdf/summary-tasks")
    assert list_response.status_code == 200
    ready_tasks = {
        task["file_id"]: task
        for task in list_response.json()["tasks"]
        if task["file_id"] in {first_file_id, second_file_id}
    }
    assert {task["status"] for task in ready_tasks.values()} == {"ready"}
    assert all(task["progress"] == 100 for task in ready_tasks.values())

    for file_id in [first_file_id, second_file_id]:
        detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
        assert detail_response.status_code == 200
        assert detail_response.json()["summary"]["status"] == "ready"


def test_pdf_summary_task_skips_non_ready_file_and_retry_generates_after_parse(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="queued-standard.pdf")

    create_response = client.post(
        "/api/pdf/summary-tasks",
        json={"file_ids": [file_id]},
    )

    assert create_response.status_code == 202
    task = create_response.json()["tasks"][0]
    assert task["status"] == "skipped"
    assert task["result"]["reason"] == "not_ready"

    upload_worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert upload_worker.run_once() is True

    retry_response = client.post(f"/api/pdf/summary-tasks/{task['task_id']}/retry")
    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["retry_count"] == 1

    summary_worker = app.dependency_overrides[get_pdf_summary_task_worker]()
    assert summary_worker.run_once() is True

    completed_response = client.get(f"/api/pdf/summary-tasks/{task['task_id']}")
    assert completed_response.status_code == 200
    completed = completed_response.json()
    assert completed["status"] == "ready"
    assert completed["result"]["summary_status"] == "ready"


def test_pdf_summary_task_failure_can_be_retried(
    client: TestClient,
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="failure-standard.pdf")
    upload_worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert upload_worker.run_once() is True

    failing_service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "failing-storage",
        parser=FakePdfParser(),
        llm_client=FailingSummaryLlmClient(),
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    failing_worker = PdfSummaryTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=failing_service,
        poll_interval_seconds=0.1,
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: failing_service
    app.dependency_overrides[get_pdf_summary_task_worker] = lambda: failing_worker
    create_response = client.post(
        "/api/pdf/summary-tasks",
        json={"file_ids": [file_id], "force": True},
    )
    assert create_response.status_code == 202
    task_id = create_response.json()["tasks"][0]["task_id"]

    assert failing_worker.run_once() is True
    failed_response = client.get(f"/api/pdf/summary-tasks/{task_id}")
    assert failed_response.status_code == 200
    failed_task = failed_response.json()
    assert failed_task["status"] == "failed"
    assert "summary llm failed" in failed_task["error_message"]

    success_service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "success-storage",
        parser=FakePdfParser(),
        llm_client=FakeLlmClient(),
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    success_worker = PdfSummaryTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=success_service,
        poll_interval_seconds=0.1,
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: success_service
    app.dependency_overrides[get_pdf_summary_task_worker] = lambda: success_worker

    retry_response = client.post(f"/api/pdf/summary-tasks/{task_id}/retry")
    assert retry_response.status_code == 202
    assert retry_response.json()["status"] == "queued"

    assert success_worker.run_once() is True
    completed_response = client.get(f"/api/pdf/summary-tasks/{task_id}")
    assert completed_response.status_code == 200
    assert completed_response.json()["status"] == "ready"


def test_pdf_summary_task_creation_reuses_active_task(client: TestClient) -> None:
    file_id = _upload_pdf(client, filename="active-task-standard.pdf")
    upload_worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert upload_worker.run_once() is True

    first_response = client.post(
        "/api/pdf/summary-tasks",
        json={"file_ids": [file_id]},
    )
    second_response = client.post(
        "/api/pdf/summary-tasks",
        json={"file_ids": [file_id]},
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert (
        second_response.json()["tasks"][0]["task_id"]
        == first_response.json()["tasks"][0]["task_id"]
    )

    cancel_response = client.post(
        f"/api/pdf/summary-tasks/{first_response.json()['tasks'][0]['task_id']}/cancel"
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_pdf_route_single_candidate_does_not_require_summary(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="route-summary-standard.pdf")
    upload_worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert upload_worker.run_once() is True
    session_response = client.post("/api/pdf/chat/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    route_without_summary = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={"question": "route-summary-standard compliance evidence"},
    )
    assert route_without_summary.status_code == 200
    assert route_without_summary.json()["selected_documents"][0]["file_id"] == file_id


def test_pdf_chat_answers_with_citations(client: TestClient) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert client.post(f"/api/pdf/files/{file_id}/summary/generate").status_code == 200

    chat_response = client.post(
        "/api/pdf/chat",
        json={
            "question": "What does the PDF say about compliance evidence?",
            "file_ids": [file_id],
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
    assert answer["selected_documents"][0]["file_id"] == file_id
    assert answer["insufficient_evidence"] is False


def test_pdf_chat_request_id_is_idempotent_within_session(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="idempotent-chat.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    request_id = "pdfreq_idempotent_0001"
    payload = {
        "question": "What evidence is in this PDF?",
        "file_ids": [file_id],
        "request_id": request_id,
    }

    first = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json=payload,
    )
    second = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json=payload,
    )
    turns = client.get(f"/api/pdf/chat/sessions/{session_id}/turns")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["request_id"] == request_id
    assert turns.status_code == 200
    assert len(turns.json()["turns"]) == 1
    assert turns.json()["turns"][0]["answer"]["request_id"] == request_id

    conflict = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={
            "question": "A different question must not reuse the request ID.",
            "file_ids": [file_id],
            "request_id": request_id,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CHAT_IDEMPOTENCY_CONFLICT"


def test_failed_pdf_chat_request_releases_idempotency_claim_for_retry(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="retryable-chat.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    class FailOnceAnswerLlmClient(FakeLlmClient):
        def __init__(self) -> None:
            self.failed = False

        def answer_with_pdf_chunks(self, *args, **kwargs):
            if not self.failed:
                self.failed = True
                raise LlmRequestError(
                    stage="pdf_answer",
                    model="test-answer",
                    provider="test-provider",
                    duration_seconds=0.1,
                    cause=RuntimeError("injected transient failure"),
                )
            return super().answer_with_pdf_chunks(*args, **kwargs)

    chat_service = PdfChatService(
        llm_client=FailOnceAnswerLlmClient(),
        sessions=pdf_repository,
    )
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
        path = f"/api/pdf/chat/sessions/{session_id}/messages"
        payload = {
            "question": "Retry this PDF request safely.",
            "file_ids": [file_id],
            "request_id": "pdf-retry-after-failure",
        }
        failed = client.post(path, json=payload)
        retried = client.post(path, json=payload)
        turns = client.get(f"/api/pdf/chat/sessions/{session_id}/turns")
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert failed.status_code == 502
    assert retried.status_code == 200
    assert [turn["question"] for turn in turns.json()["turns"]] == [
        payload["question"]
    ]


def test_pdf_chat_server_cancellation_prevents_turn_persistence(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="cancelled-chat.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    request_id = "pdfreq_cancelled_0001"

    cancel_response = client.post(
        "/api/pdf/chat/cancel",
        json={"request_id": request_id},
    )
    answer_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={
            "question": "This request must not be persisted.",
            "file_ids": [file_id],
            "request_id": request_id,
        },
    )
    turns = client.get(f"/api/pdf/chat/sessions/{session_id}/turns")

    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancelled"] is True
    assert answer_response.status_code == 499
    assert answer_response.json()["code"] == "CHAT_REQUEST_CANCELLED"
    assert turns.status_code == 200
    assert turns.json()["turns"] == []


def test_pdf_chat_single_candidate_skips_router(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="direct-scope.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    llm_client = RecordingPdfLlmClient()
    chat_service = PdfChatService(
        llm_client=llm_client,
        sessions=pdf_repository,
    )
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        assert session_response.status_code == 200
        answer_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/messages",
            json={
                "question": "PDF",
                "file_ids": [file_id],
            },
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert answer_response.status_code == 200
    answer = answer_response.json()
    assert {document["file_id"] for document in answer["selected_documents"]} == {file_id}
    assert llm_client.route_calls == []


def test_pdf_chat_persists_scope_and_uses_first_question_as_session_title(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="persistent-scope.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    session_response = client.post("/api/pdf/chat/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]
    question = "What compliance evidence does this PDF contain?"

    answer_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={
            "question": question,
            "file_ids": [file_id],
        },
    )
    assert answer_response.status_code == 200

    detail_response = client.get(f"/api/pdf/chat/sessions/{session_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["context_file_ids"] == [file_id]
    assert detail_response.json()["title"] == question

    listed_sessions = client.get("/api/pdf/chat/sessions").json()["sessions"]
    listed_session = next(
        session for session in listed_sessions if session["session_id"] == session_id
    )
    assert listed_session["context_file_ids"] == [file_id]
    assert listed_session["title"] == question


def test_pdf_summary_route_preview_and_integrated_answer_flow(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="safety-standard.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert client.post(f"/api/pdf/files/{file_id}/summary/generate").status_code == 200

    session_response = client.post("/api/pdf/chat/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    route_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={
            "question": "Which compliance evidence does safety-standard.pdf mention?",
            "file_ids": [file_id],
        },
    )

    assert route_response.status_code == 200
    route = route_response.json()
    assert route["selected_documents"][0]["file_id"] == file_id
    assert route["selected_documents"][0]["version_id"] == file_id
    assert route["newly_attached_documents"][0]["file_id"] == file_id
    assert route["attached_documents"][0]["file_id"] == file_id
    assert route["attached_documents"][0]["chunk_count"] >= 1

    answer_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={
            "question": "Which compliance evidence does safety-standard.pdf mention?",
            "file_ids": [file_id],
        },
    )

    assert answer_response.status_code == 200
    answer = answer_response.json()
    assert answer["session_id"] == session_id
    assert answer["selected_documents"][0]["file_id"] == file_id
    assert answer["attached_documents"][0]["file_id"] == file_id
    assert answer["citations"][0]["file_id"] == file_id

    turns_response = client.get(f"/api/pdf/chat/sessions/{session_id}/turns")
    assert turns_response.status_code == 200
    turn_answer = turns_response.json()["turns"][0]["answer"]
    assert turn_answer["selected_documents"][0]["file_id"] == file_id
    assert turn_answer["citations"][0]["file_id"] == file_id


def test_pdf_chat_folder_scope_limits_route_and_answer(
    client: TestClient,
) -> None:
    upload_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/standard-a.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/b/standard-b.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert upload_response.status_code == 202
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True

    files = client.get("/api/pdf/files").json()["files"]
    root_folder = _find_pdf_file(files, name="root", kind="folder")
    folder_a = _find_pdf_file(files, name="a", kind="folder", parent_id=root_folder["file_id"])
    folder_b = _find_pdf_file(files, name="b", kind="folder", parent_id=root_folder["file_id"])
    file_a = _find_pdf_file(files, name="standard-a.pdf", kind="pdf", parent_id=folder_a["file_id"])
    file_b = _find_pdf_file(files, name="standard-b.pdf", kind="pdf", parent_id=folder_b["file_id"])

    session_response = client.post("/api/pdf/chat/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    route_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={
            "question": "Which Knowledge Index evidence is available?",
            "file_ids": [folder_a["file_id"]],
        },
    )
    assert route_response.status_code == 200
    route = route_response.json()
    assert {document["file_id"] for document in route["selected_documents"]} == {
        file_a["file_id"]
    }
    assert {document["file_id"] for document in route["attached_documents"]} == {
        file_a["file_id"]
    }

    answer_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={
            "question": "Which Knowledge Index evidence is available?",
            "file_ids": [folder_a["file_id"]],
        },
    )
    assert answer_response.status_code == 200
    answer = answer_response.json()
    assert {document["file_id"] for document in answer["selected_documents"]} == {
        file_a["file_id"]
    }
    assert {citation["file_id"] for citation in answer["citations"]} == {
        file_a["file_id"]
    }
    assert file_b["file_id"] not in {
        citation["file_id"] for citation in answer["citations"]
    }


def test_pdf_folder_router_is_scope_bound_and_capped_at_nine_documents(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    scoped_paths = [f"root/scoped/document-{index}.pdf" for index in range(10)]
    upload_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            *[
                ("files", (path, _pdf_bytes(), "application/pdf"))
                for path in scoped_paths
            ],
            (
                "files",
                ("root/outside/outside.pdf", _pdf_bytes(), "application/pdf"),
            ),
        ],
    )
    assert upload_response.status_code == 202
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    for _ in upload_response.json()["tasks"]:
        assert worker.run_once() is True
    pending_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            (
                "files",
                ("root/scoped/pending.pdf", _pdf_bytes(), "application/pdf"),
            )
        ],
    )
    assert pending_response.status_code == 202
    pending_file_id = pending_response.json()["tasks"][0]["file_id"]

    files = client.get("/api/pdf/files").json()["files"]
    root_folder = _find_pdf_file(files, name="root", kind="folder")
    scoped_folder = _find_pdf_file(
        files,
        name="scoped",
        kind="folder",
        parent_id=root_folder["file_id"],
    )
    outside_folder = _find_pdf_file(
        files,
        name="outside",
        kind="folder",
        parent_id=root_folder["file_id"],
    )
    scoped_file_ids = [
        str(file["file_id"])
        for file in files
        if file["kind"] == "pdf"
        and file["parent_id"] == scoped_folder["file_id"]
        and file["processing_status"] == "ready"
    ]
    outside_file = _find_pdf_file(
        files,
        name="outside.pdf",
        kind="pdf",
        parent_id=outside_folder["file_id"],
    )

    question = "Select the relevant scoped documents."
    llm_client = RoutingProbePdfLlmClient(
        {
            question: [
                *scoped_file_ids,
                str(pending_file_id),
                str(outside_file["file_id"]),
            ]
        }
    )
    chat_service = PdfChatService(llm_client=llm_client, sessions=pdf_repository)
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        route_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/route",
            json={"question": question, "file_ids": [scoped_folder["file_id"]]},
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert route_response.status_code == 200
    request = llm_client.route_requests[0]
    assert set(request["candidate_file_ids"]) == set(scoped_file_ids)
    assert pending_file_id not in request["candidate_file_ids"]
    assert outside_file["file_id"] not in request["candidate_file_ids"]
    assert request["max_documents"] == 9
    duplicate_groups = request["duplicate_content_groups"]
    assert all(duplicate_groups)
    assert len(set(duplicate_groups)) == 1
    selected_file_ids = {
        document["file_id"] for document in route_response.json()["selected_documents"]
    }
    assert len(selected_file_ids) == 9
    assert selected_file_ids.issubset(set(scoped_file_ids))


def test_pdf_all_sources_passes_every_visible_ready_candidate_to_router(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_file_id = _upload_pdf(client, filename="all-sources-first.pdf")
    second_file_id = _upload_pdf(client, filename="all-sources-second.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True
    first_file = pdf_repository.get_pdf_file(first_file_id)
    second_file = pdf_repository.get_pdf_file(second_file_id)
    assert first_file is not None
    assert second_file is not None
    assert first_file.content_fingerprint
    assert first_file.content_fingerprint == second_file.content_fingerprint

    def fail_individual_chunk_query(_file_id: str):
        raise AssertionError("routing must use the batch PDF chunk query")

    monkeypatch.setattr(
        pdf_repository,
        "list_pdf_document_chunks",
        fail_individual_chunk_query,
    )

    question = "Select the matching document from all PDF sources."
    llm_client = RoutingProbePdfLlmClient({question: [second_file_id]})
    chat_service = PdfChatService(llm_client=llm_client, sessions=pdf_repository)
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        route_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/route",
            json={"question": question, "file_ids": []},
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert route_response.status_code == 200
    assert len(llm_client.route_requests) == 1
    assert set(llm_client.route_requests[0]["candidate_file_ids"]) == {
        first_file_id,
        second_file_id,
    }
    assert {
        document["file_id"]
        for document in route_response.json()["selected_documents"]
    } == {second_file_id}


def test_pdf_chat_gives_each_of_nine_selected_documents_grounding_context(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_ids = [
        _upload_pdf(client, filename=f"coverage-{index}.pdf")
        for index in range(9)
    ]
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    for _file_id in file_ids:
        assert worker.run_once() is True

    question = "Compare the evidence across all nine documents."
    llm_client = ContextRecordingPdfLlmClient({question: file_ids})
    chat_service = PdfChatService(llm_client=llm_client, sessions=pdf_repository)
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
        answer_response = client.post(
            f"/api/pdf/chat/sessions/{session_id}/messages",
            json={"question": question, "file_ids": []},
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert answer_response.status_code == 200
    assert len(answer_response.json()["selected_documents"]) == 9
    assert set(llm_client.answer_chunk_file_ids) == set(file_ids)


def test_pdf_router_format_failure_returns_typed_retryable_error(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    _upload_pdf(client, filename="router-error-first.pdf")
    _upload_pdf(client, filename="router-error-second.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True

    class InvalidRouterResponseLlmClient(FakeLlmClient):
        def route_pdf_documents(self, *args, **kwargs):
            _ = args, kwargs
            raise PdfRoutingError()

    chat_service = PdfChatService(
        llm_client=InvalidRouterResponseLlmClient(),
        sessions=pdf_repository,
    )
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        route_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/route",
            json={"question": "Trigger typed router failure.", "file_ids": []},
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert route_response.status_code == 502
    assert route_response.json() == {
        "code": "PDF_ROUTER_INVALID_RESPONSE",
        "detail": "PDF document routing failed. Please retry.",
        "retryable": True,
    }


def test_pdf_multiturn_reroutes_within_current_scope_without_attachment_fallback(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    upload_response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[
            ("files", ("root/a/a-one.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/a/a-two.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/b/b-one.pdf", _pdf_bytes(), "application/pdf")),
            ("files", ("root/b/b-two.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )
    assert upload_response.status_code == 202
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    for _ in upload_response.json()["tasks"]:
        assert worker.run_once() is True

    files = client.get("/api/pdf/files").json()["files"]
    root_folder = _find_pdf_file(files, name="root", kind="folder")
    folder_a = _find_pdf_file(files, name="a", kind="folder", parent_id=root_folder["file_id"])
    folder_b = _find_pdf_file(files, name="b", kind="folder", parent_id=root_folder["file_id"])
    file_a = _find_pdf_file(
        files,
        name="a-one.pdf",
        kind="pdf",
        parent_id=folder_a["file_id"],
    )
    file_b = _find_pdf_file(
        files,
        name="b-one.pdf",
        kind="pdf",
        parent_id=folder_b["file_id"],
    )

    first_question = "Use the first folder."
    second_question = "Now use the second folder."
    no_match_question = "No document matches this follow-up."
    llm_client = RoutingProbePdfLlmClient(
        {
            first_question: [str(file_a["file_id"])],
            second_question: [str(file_b["file_id"])],
            no_match_question: [],
        }
    )
    chat_service = PdfChatService(llm_client=llm_client, sessions=pdf_repository)
    original_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        session_id = session_response.json()["session_id"]
        first_answer = client.post(
            f"/api/pdf/chat/sessions/{session_id}/messages",
            json={"question": first_question, "file_ids": [folder_a["file_id"]]},
        )
        second_answer = client.post(
            f"/api/pdf/chat/sessions/{session_id}/messages",
            json={"question": second_question, "file_ids": [folder_b["file_id"]]},
        )
        no_match_answer = client.post(
            f"/api/pdf/chat/sessions/{session_id}/messages",
            json={"question": no_match_question, "file_ids": [folder_b["file_id"]]},
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_override

    assert first_answer.status_code == 200
    assert {citation["file_id"] for citation in first_answer.json()["citations"]} == {
        file_a["file_id"]
    }
    assert second_answer.status_code == 200
    assert {citation["file_id"] for citation in second_answer.json()["citations"]} == {
        file_b["file_id"]
    }
    assert llm_client.route_requests[1]["previous_questions"] == [first_question]
    assert llm_client.answer_requests[1]["previous_questions"] == [first_question]
    assert llm_client.answer_requests[1]["previous_answers"]
    assert llm_client.answer_requests[1]["previous_citation_ids"]
    assert llm_client.answer_requests[1]["previous_selected_file_ids"] == [
        [file_a["file_id"]]
    ]
    assert no_match_answer.status_code == 200
    no_match = no_match_answer.json()
    assert no_match["selected_documents"] == []
    assert no_match["citations"] == []
    assert no_match["insufficient_evidence"] is True
    assert llm_client.route_requests[2]["previous_questions"] == [
        first_question,
        second_question,
    ]


def test_pdf_route_excludes_hidden_and_deleted_documents_for_member(
    client: TestClient,
) -> None:
    visible_file_id = _upload_pdf(client, filename="visible-standard.pdf")
    hidden_file_id = _upload_pdf(client, filename="hidden-standard.pdf")
    deleted_file_id = _upload_pdf(client, filename="deleted-standard.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True
    assert worker.run_once() is True
    assert client.post(f"/api/pdf/files/{visible_file_id}/summary/generate").status_code == 200
    assert client.post(f"/api/pdf/files/{hidden_file_id}/summary/generate").status_code == 200
    assert client.post(f"/api/pdf/files/{deleted_file_id}/summary/generate").status_code == 200

    assert client.patch(
        f"/api/pdf/files/{hidden_file_id}/visibility",
        json={"visible_to_members": False},
    ).status_code == 200
    assert client.delete(
        f"/api/pdf/files/{deleted_file_id}?confirm_delete=true"
    ).status_code == 200

    app.dependency_overrides[get_current_user] = member_user
    try:
        session_response = client.post("/api/pdf/chat/sessions")
        assert session_response.status_code == 200
        route_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/route",
            json={
                "question": "Which compliance evidence is mentioned?",
                "file_ids": [],
            },
        )
        explicit_hidden_response = client.post(
            f"/api/pdf/chat/sessions/{session_response.json()['session_id']}/route",
            json={
                "question": "Which compliance evidence is mentioned?",
                "file_ids": [hidden_file_id],
            },
        )
    finally:
        app.dependency_overrides[get_current_user] = admin_user

    assert route_response.status_code == 200
    selected_file_ids = {
        document["file_id"]
        for document in route_response.json()["selected_documents"]
    }
    assert selected_file_ids == {visible_file_id}
    assert route_response.json()["attached_documents"][0]["file_id"] == visible_file_id
    assert explicit_hidden_response.status_code == 404


def test_pdf_chat_revalidates_visibility_after_model_answer(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="visibility-race.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    llm_client = VisibilityHidingPdfLlmClient(
        repository=pdf_repository,
        file_id=file_id,
    )
    chat_service = PdfChatService(llm_client=llm_client, sessions=pdf_repository)
    original_chat_override = app.dependency_overrides[get_pdf_chat_service]
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    app.dependency_overrides[get_current_user] = member_user
    try:
        session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
        answer_response = client.post(
            f"/api/pdf/chat/sessions/{session_id}/messages",
            json={
                "question": "Use the temporarily visible PDF.",
                "file_ids": [file_id],
            },
        )
    finally:
        app.dependency_overrides[get_pdf_chat_service] = original_chat_override
        app.dependency_overrides[get_current_user] = admin_user

    assert answer_response.status_code == 200
    answer = answer_response.json()
    assert llm_client.answer_calls == 1
    assert answer["insufficient_evidence"] is True
    assert answer["selected_documents"] == []
    assert answer["citations"] == []
    assert answer["answer_blocks"][0]["citation_ids"] == []
    assert answer["warnings"]


def test_pdf_chat_session_can_be_listed_renamed_pinned_and_deleted(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client)
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert client.post(f"/api/pdf/files/{file_id}/summary/generate").status_code == 200

    first_response = client.post("/api/pdf/chat/sessions")
    second_response = client.post("/api/pdf/chat/sessions")
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_session_id = first_response.json()["session_id"]
    second_session_id = second_response.json()["session_id"]

    answer_response = client.post(
        f"/api/pdf/chat/sessions/{first_session_id}/messages",
        json={
            "question": "What does the PDF say about compliance evidence?",
            "file_ids": [file_id],
        },
    )
    assert answer_response.status_code == 200
    assert answer_response.json()["session_id"] == first_session_id

    rename_response = client.patch(
        f"/api/pdf/chat/sessions/{first_session_id}",
        json={"title": "PDF Compliance Review"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "PDF Compliance Review"

    pin_response = client.patch(
        f"/api/pdf/chat/sessions/{first_session_id}/pin",
        json={"pinned": True},
    )
    assert pin_response.status_code == 200
    assert pin_response.json()["pinned_at"] is not None

    list_response = client.get("/api/pdf/chat/sessions")
    assert list_response.status_code == 200
    assert [session["session_id"] for session in list_response.json()["sessions"]] == [
        first_session_id,
        second_session_id,
    ]

    turns_response = client.get(f"/api/pdf/chat/sessions/{first_session_id}/turns")
    assert turns_response.status_code == 200
    assert turns_response.json()["turns"][0]["answer"]["citations"][0]["file_id"] == file_id

    delete_response = client.delete(f"/api/pdf/chat/sessions/{first_session_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/pdf/chat/sessions/{first_session_id}").status_code == 404


def test_pdf_chat_session_mutations_reject_stale_revisions(
    client: TestClient,
) -> None:
    session = client.post("/api/pdf/chat/sessions").json()
    session_id = session["session_id"]

    renamed = client.patch(
        f"/api/pdf/chat/sessions/{session_id}",
        json={
            "title": "Revision protected",
            "expected_revision": session["revision"],
        },
    )
    assert renamed.status_code == 200
    assert renamed.json()["revision"] == session["revision"] + 1

    stale_pin = client.patch(
        f"/api/pdf/chat/sessions/{session_id}/pin",
        json={
            "pinned": True,
            "expected_revision": session["revision"],
        },
    )
    assert stale_pin.status_code == 409
    assert stale_pin.json()["code"] == "CHAT_SESSION_REVISION_CONFLICT"

    stale_delete = client.delete(
        f"/api/pdf/chat/sessions/{session_id}",
        params={"expected_revision": session["revision"]},
    )
    assert stale_delete.status_code == 409
    assert client.get(f"/api/pdf/chat/sessions/{session_id}").status_code == 200


def test_pdf_chat_session_batch_mutations_are_atomic_and_workspace_scoped(
    client: TestClient,
) -> None:
    first = client.post("/api/pdf/chat/sessions").json()
    second = client.post("/api/pdf/chat/sessions").json()
    excel = client.post("/api/excel/chat/sessions").json()

    renamed_second = client.patch(
        f"/api/pdf/chat/sessions/{second['session_id']}",
        json={
            "title": "Updated second",
            "expected_revision": second["revision"],
        },
    ).json()

    stale_batch = client.post(
        "/api/pdf/chat/sessions/batch",
        json={
            "action": "pin",
            "items": [
                {
                    "session_id": first["session_id"],
                    "expected_revision": first["revision"],
                },
                {
                    "session_id": second["session_id"],
                    "expected_revision": second["revision"],
                },
            ],
        },
    )
    assert stale_batch.status_code == 409
    assert client.get(
        f"/api/pdf/chat/sessions/{first['session_id']}"
    ).json()["pinned_at"] is None

    cross_workspace = client.post(
        "/api/pdf/chat/sessions/batch",
        json={
            "action": "delete",
            "items": [
                {
                    "session_id": first["session_id"],
                    "expected_revision": first["revision"],
                },
                {
                    "session_id": excel["session_id"],
                    "expected_revision": excel["revision"],
                },
            ],
        },
    )
    assert cross_workspace.status_code == 404
    assert client.get(f"/api/pdf/chat/sessions/{first['session_id']}").status_code == 200

    pin_batch = client.post(
        "/api/pdf/chat/sessions/batch",
        json={
            "action": "pin",
            "items": [
                {
                    "session_id": first["session_id"],
                    "expected_revision": first["revision"],
                },
                {
                    "session_id": second["session_id"],
                    "expected_revision": renamed_second["revision"],
                },
            ],
        },
    )
    assert pin_batch.status_code == 200
    updated = {
        session["session_id"]: session
        for session in pin_batch.json()["updated_sessions"]
    }
    assert set(updated) == {first["session_id"], second["session_id"]}
    assert all(session["pinned_at"] is not None for session in updated.values())

    delete_batch = client.post(
        "/api/pdf/chat/sessions/batch",
        json={
            "action": "delete",
            "items": [
                {
                    "session_id": session_id,
                    "expected_revision": session["revision"],
                }
                for session_id, session in updated.items()
            ],
        },
    )
    assert delete_batch.status_code == 200
    assert set(delete_batch.json()["deleted_session_ids"]) == {
        first["session_id"],
        second["session_id"],
    }
    assert client.get(f"/api/pdf/chat/sessions/{first['session_id']}").status_code == 404
    assert client.get(f"/api/pdf/chat/sessions/{second['session_id']}").status_code == 404
    assert client.get(f"/api/excel/chat/sessions/{excel['session_id']}").status_code == 200


def test_pdf_and_excel_chat_sessions_are_isolated(client: TestClient) -> None:
    pdf_session = client.post("/api/pdf/chat/sessions")
    excel_session = client.post("/api/excel/chat/sessions")
    assert pdf_session.status_code == 200
    assert excel_session.status_code == 200

    pdf_list = client.get("/api/pdf/chat/sessions")
    excel_list = client.get("/api/excel/chat/sessions")

    assert [session["session_id"] for session in pdf_list.json()["sessions"]] == [
        pdf_session.json()["session_id"]
    ]
    assert [session["session_id"] for session in excel_list.json()["sessions"]] == [
        excel_session.json()["session_id"]
    ]


def test_pdf_model_settings_can_be_listed_and_updated(client: TestClient) -> None:
    list_response = client.get("/api/pdf/model-settings")
    assert list_response.status_code == 200
    settings = list_response.json()["settings"]
    assert [setting["id"] for setting in settings] == ["summary", "router", "chat"]
    assert settings[0]["providers"] == [
        provider["provider"]
        for provider in list_supported_llm_provider_options()
    ]
    assert settings[0]["models"] == list_supported_llm_models()
    assert settings[0]["provider_models"] == {
        provider["provider"]: provider["models"]
        for provider in list_supported_llm_provider_options()
    }
    assert settings[0]["selected_provider"] == DEFAULT_SUMMARY_PROVIDER
    assert settings[0]["selected_model"] == DEFAULT_SUMMARY_MODEL
    assert settings[1]["selected_provider"] == DEFAULT_ROUTER_PROVIDER
    assert settings[1]["selected_model"] == DEFAULT_ROUTER_MODEL
    assert settings[2]["selected_provider"] == DEFAULT_ANSWER_PROVIDER
    assert settings[2]["selected_model"] == DEFAULT_ANSWER_MODEL

    patch_response = client.patch(
        "/api/pdf/model-settings/summary",
        json={
            "selected_provider": SILICONFLOW_PROVIDER,
            "selected_model": "deepseek-ai/DeepSeek-V4-Flash",
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["settings"][0]
    assert updated["id"] == "summary"
    assert updated["selected_provider"] == SILICONFLOW_PROVIDER
    assert updated["selected_model"] == "deepseek-ai/DeepSeek-V4-Flash"


def test_pdf_model_settings_reject_unsupported_provider_model_pairs(
    client: TestClient,
) -> None:
    provider_response = client.patch(
        "/api/pdf/model-settings/summary",
        json={
            "selected_provider": "unknown-provider",
            "selected_model": DEFAULT_SUMMARY_MODEL,
        },
    )
    assert provider_response.status_code == 422

    model_response = client.patch(
        "/api/pdf/model-settings/summary",
        json={
            "selected_provider": DEFAULT_SUMMARY_PROVIDER,
            "selected_model": "deepseek-ai/DeepSeek-V4-Pro",
        },
    )
    assert model_response.status_code == 422


def test_pdf_model_settings_normalize_legacy_saved_values(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    now = "2026-01-01T00:00:00Z"
    pdf_repository.save_pdf_model_setting(
        PdfModelSetting(
            setting_id="summary",
            label="Summary Engine",
            providers=["SiliconFlow", "DeepSeek"],
            models=["deepseek-v3", "gpt-4o"],
            selected_provider="DeepSeek",
            selected_model="gpt-4o",
            created_at=now,
            updated_at=now,
        )
    )

    response = client.get("/api/pdf/model-settings")
    assert response.status_code == 200
    setting = response.json()["settings"][0]
    assert setting["selected_provider"] == DEFAULT_SUMMARY_PROVIDER
    assert setting["selected_model"] == DEFAULT_SUMMARY_MODEL
    assert setting["providers"] == [
        provider["provider"]
        for provider in list_supported_llm_provider_options()
    ]
    assert setting["models"] == list_supported_llm_models()


def test_pdf_model_settings_are_used_by_summary_route_and_answer(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    llm_client = RecordingPdfLlmClient()
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=FakePdfParser(),
        parser_status=PdfParserRuntimeStatus(
            backend="fake",
            available=True,
            detail="Fake parser for model setting tests.",
        ),
        llm_client=llm_client,
        llm_preferences=WorkspaceLlmPreferenceService(
            repository=pdf_repository,
            settings=Settings(llm_provider="fake"),
        ),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    chat_service = PdfChatService(
        llm_client=llm_client,
        sessions=pdf_repository,
    )
    app.dependency_overrides[get_pdf_knowledge_service] = lambda: service
    app.dependency_overrides[get_pdf_upload_task_worker] = lambda: worker
    app.dependency_overrides[get_pdf_chat_service] = lambda: chat_service
    app.dependency_overrides[get_current_user] = admin_user
    app.dependency_overrides[require_admin_user] = admin_user
    try:
        with TestClient(app) as test_client:
            file_id = _upload_pdf(test_client, filename="configured-model.pdf")
            other_file_id = _upload_pdf(test_client, filename="other-document.pdf")
            assert worker.run_once() is True
            assert worker.run_once() is True

            expected_settings = {
                "summary": ("deepseek", "deepseek-v4-flash"),
                "router": ("siliconflow", "Qwen/Qwen3.6-35B-A3B"),
                "chat": ("deepseek", "deepseek-v4-pro"),
            }
            for setting_id, (provider, model) in expected_settings.items():
                response = test_client.patch(
                    f"/api/pdf/model-settings/{setting_id}",
                    json={
                        "selected_provider": provider,
                        "selected_model": model,
                    },
                )
                assert response.status_code == 200

            summary_response = test_client.post(
                f"/api/pdf/files/{file_id}/summary/generate"
            )
            assert summary_response.status_code == 200
            assert test_client.post(
                f"/api/pdf/files/{other_file_id}/summary/generate"
            ).status_code == 200

            session_response = test_client.post("/api/pdf/chat/sessions")
            assert session_response.status_code == 200
            session_id = session_response.json()["session_id"]

            route_response = test_client.post(
                f"/api/pdf/chat/sessions/{session_id}/route",
                json={
                    "question": "Which compliance evidence is configured-model about?",
                    "file_ids": [],
                },
            )
            assert route_response.status_code == 200

            answer_response = test_client.post(
                f"/api/pdf/chat/sessions/{session_id}/messages",
                json={
                    "question": "Which compliance evidence is configured-model about?",
                    "file_ids": [],
                },
            )
            assert answer_response.status_code == 200

        assert llm_client.summary_calls[-1] == {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
        }
        assert llm_client.route_calls[-1] == {
            "provider": "siliconflow",
            "model": "Qwen/Qwen3.6-35B-A3B",
        }
        assert llm_client.answer_calls[-1] == {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
        }
    finally:
        app.dependency_overrides.clear()


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


def test_pdf_retrieval_endpoint_is_not_registered(client: TestClient) -> None:
    response = client.post(
        "/api/pdf/retrieval/search",
        json={"query": "compliance"},
    )
    assert response.status_code == 404


def test_pdf_session_snapshot_returns_owned_session_and_turns_without_mutation(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    committed = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={"question": "Summarize the available evidence.", "file_ids": []},
    )
    assert committed.status_code == 200
    before = pdf_repository.get_session(session_id, workspace="pdf")
    assert before is not None

    response = client.get(f"/api/pdf/chat/sessions/{session_id}/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["session_id"] == session_id
    assert [turn["question"] for turn in payload["turns"]] == [
        "Summarize the available evidence."
    ]
    after = pdf_repository.get_session(session_id, workspace="pdf")
    assert after == before


def test_pdf_session_snapshot_hides_missing_foreign_and_excel_sessions(
    client: TestClient,
) -> None:
    pdf_session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    excel_session_id = client.post("/api/excel/chat/sessions").json()["session_id"]

    assert client.get("/api/pdf/chat/sessions/missing/snapshot").status_code == 404
    assert (
        client.get(f"/api/pdf/chat/sessions/{excel_session_id}/snapshot").status_code
        == 404
    )

    app.dependency_overrides[get_current_user] = member_user
    try:
        foreign_response = client.get(
            f"/api/pdf/chat/sessions/{pdf_session_id}/snapshot"
        )
    finally:
        app.dependency_overrides[get_current_user] = admin_user
    assert foreign_response.status_code == 404


def test_pdf_document_chunk_endpoint_enforces_file_and_visibility_scope(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="chunk-evidence.pdf")
    other_file_id = _upload_pdf(client, filename="other-evidence.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True
    chunk = pdf_repository.list_pdf_document_chunks(file_id)[0]

    response = client.get(f"/api/pdf/files/{file_id}/chunks/{chunk.chunk_id}")
    assert response.status_code == 200
    assert response.json()["chunk_id"] == chunk.chunk_id
    assert (
        client.get(
            f"/api/pdf/files/{other_file_id}/chunks/{chunk.chunk_id}"
        ).status_code
        == 404
    )

    hidden = client.patch(
        f"/api/pdf/files/{file_id}/visibility",
        json={"visible_to_members": False},
    )
    assert hidden.status_code == 200
    app.dependency_overrides[get_current_user] = member_user
    try:
        hidden_response = client.get(
            f"/api/pdf/files/{file_id}/chunks/{chunk.chunk_id}"
        )
    finally:
        app.dependency_overrides[get_current_user] = admin_user
    assert hidden_response.status_code == 404


def test_pdf_route_is_side_effect_free_and_split_answer_commits_atomically(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    file_id = _upload_pdf(client, filename="split-chat.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    session_response = client.post("/api/pdf/chat/sessions")
    assert session_response.status_code == 200
    session_id = session_response.json()["session_id"]

    route_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={
            "question": "compliance",
            "file_ids": [file_id],
        },
    )
    route = route_response.json()

    assert route_response.status_code == 200
    assert route["context_file_ids"] == [file_id]
    assert route["session_revision"] == 0
    assert route["selected_documents"][0]["file_id"] == file_id
    assert pdf_repository.list_pdf_attached_documents(session_id) == []
    assert pdf_repository.list_turns(session_id, workspace="pdf") == []

    answer_response = client.post(
        f"/api/pdf/chat/sessions/{session_id}/answer",
        json={
            "question": route["question"],
            "selected_file_ids": [
                document["file_id"] for document in route["selected_documents"]
            ],
            "file_ids": route["context_file_ids"],
            "session_revision": route["session_revision"],
            "request_id": "pdf-split-answer-request",
        },
    )

    assert answer_response.status_code == 200
    assert answer_response.json()["citations"][0]["file_id"] == file_id
    assert len(pdf_repository.list_pdf_attached_documents(session_id)) == 1
    assert len(pdf_repository.list_turns(session_id, workspace="pdf")) == 1


def test_pdf_split_answer_rejects_stale_conversation_revision(
    client: TestClient,
) -> None:
    file_id = _upload_pdf(client, filename="stale-route.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    route = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={"question": "Plan this answer.", "file_ids": [file_id]},
    ).json()
    committed = client.post(
        f"/api/pdf/chat/sessions/{session_id}/messages",
        json={"question": "Commit another turn.", "file_ids": [file_id]},
    )
    stale = client.post(
        f"/api/pdf/chat/sessions/{session_id}/answer",
        json={
            "question": route["question"],
            "selected_file_ids": [
                document["file_id"] for document in route["selected_documents"]
            ],
            "file_ids": route["context_file_ids"],
            "session_revision": route["session_revision"],
            "request_id": "pdf-stale-answer-request",
        },
    )

    assert committed.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "CHAT_SESSION_REVISION_CONFLICT"


def test_pdf_split_answer_cannot_escape_the_routed_hard_scope(
    client: TestClient,
) -> None:
    scoped_file_id = _upload_pdf(client, filename="scope-a.pdf")
    outside_file_id = _upload_pdf(client, filename="scope-b.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True
    assert worker.run_once() is True
    session_id = client.post("/api/pdf/chat/sessions").json()["session_id"]
    route = client.post(
        f"/api/pdf/chat/sessions/{session_id}/route",
        json={"question": "Use only scope A.", "file_ids": [scoped_file_id]},
    ).json()

    answer = client.post(
        f"/api/pdf/chat/sessions/{session_id}/answer",
        json={
            "question": route["question"],
            "selected_file_ids": [outside_file_id],
            "file_ids": route["context_file_ids"],
            "session_revision": route["session_revision"],
            "request_id": "pdf-hard-scope-answer",
        },
    )

    assert answer.status_code == 200
    assert answer.json()["selected_documents"] == []
    assert answer.json()["citations"] == []
    assert answer.json()["insufficient_evidence"] is True


def test_unknown_pdf_chat_session_is_never_created_implicitly(
    client: TestClient,
) -> None:
    sessions_before = client.get("/api/pdf/chat/sessions").json()["sessions"]
    missing_session_id = "pdfsession_missing"

    message = client.post(
        f"/api/pdf/chat/sessions/{missing_session_id}/messages",
        json={
            "question": "Do not create this session.",
            "request_id": "pdf-missing-message",
        },
    )
    route = client.post(
        f"/api/pdf/chat/sessions/{missing_session_id}/route",
        json={
            "question": "Do not create this session.",
            "request_id": "pdf-missing-route",
        },
    )
    answer = client.post(
        f"/api/pdf/chat/sessions/{missing_session_id}/answer",
        json={
            "question": "Do not create this session.",
            "selected_file_ids": [],
            "file_ids": [],
            "session_revision": 0,
            "request_id": "pdf-missing-answer",
        },
    )
    sessions_after = client.get("/api/pdf/chat/sessions").json()["sessions"]

    assert message.status_code == 404
    assert route.status_code == 404
    assert answer.status_code == 404
    assert sessions_after == sessions_before


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
    list_files = pdf_repository.list_pdf_files()
    failed_file_from_list = next(file for file in list_files if file.file_id == task.file_id)
    assert failed_file_from_list.quality_status == PdfParseQualityStatus.FAILED
    assert failed_file_from_list.failed_page_count == 1
    report = pdf_repository.get_pdf_parse_report(str(task.file_id))
    assert report is not None
    assert report.quality_status == PdfParseQualityStatus.FAILED
    assert report.failed_pages == 1
    assert "parser exploded" in report.warnings[0]


def test_pdf_worker_marks_partial_parse_quality(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=PartialPdfParser(),
        parser_status=PdfParserRuntimeStatus(
            backend="partial-test",
            available=True,
            detail="Partial parser for tests.",
        ),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    task = service.create_upload_task(
        user_id=admin_user().user_id,
        original_filename="partial.pdf",
        content=_pdf_bytes(),
    )

    assert worker.run_once() is True

    parsed_file = pdf_repository.get_pdf_file(str(task.file_id))
    report = pdf_repository.get_pdf_parse_report(str(task.file_id))
    completed_task = pdf_repository.get_pdf_upload_task(task.task_id)
    assert parsed_file is not None
    assert parsed_file.processing_status == PdfProcessingStatus.PARTIAL
    assert "incomplete coverage" in parsed_file.status_detail
    parsed_file_from_list = next(
        file for file in pdf_repository.list_pdf_files() if file.file_id == task.file_id
    )
    assert parsed_file_from_list.quality_status == PdfParseQualityStatus.PARTIAL
    assert parsed_file_from_list.warning_count == 1
    assert parsed_file_from_list.failed_page_count == 1
    assert parsed_file_from_list.parser_backend == "partial-test"
    assert report is not None
    assert parsed_file_from_list.coverage_ratio == report.coverage_ratio
    assert report.quality_status == PdfParseQualityStatus.PARTIAL
    assert report.failed_pages == 1
    assert report.warning_count == 1
    assert report.artifacts[0].name == "partial.md"
    assert completed_task is not None
    assert completed_task.result["quality_status"] == "partial"
    assert completed_task.result["failed_page_count"] == 1
    assert completed_task.detail == parsed_file.status_detail


def test_pdf_worker_archives_parser_artifacts(
    tmp_path: Path,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    artifact_root = tmp_path / "parser-output"
    artifact_root.mkdir()
    (artifact_root / "document.md").write_text("Parsed markdown", encoding="utf-8")
    service = PdfKnowledgeService(
        repository=pdf_repository,
        storage_root=tmp_path / "storage",
        parser=ArtifactPdfParser(artifact_root=artifact_root),
        parser_status=PdfParserRuntimeStatus(
            backend="artifact-test",
            available=True,
            detail="Artifact parser for tests.",
        ),
    )
    worker = PdfUploadTaskWorker(
        repository=pdf_repository,
        pdf_knowledge=service,
        storage_root=tmp_path / "storage",
        poll_interval_seconds=0.1,
    )
    task = service.create_upload_task(
        user_id=admin_user().user_id,
        original_filename="artifact.pdf",
        content=_pdf_bytes(),
    )

    assert worker.run_once() is True

    report = pdf_repository.get_pdf_parse_report(str(task.file_id))
    assert report is not None
    assert report.artifacts
    artifact = report.artifacts[0]
    assert artifact.path is not None
    assert artifact.path.startswith(f"pdf-knowledge/files/{task.file_id}/artifacts/")
    archived_path = tmp_path / "storage" / artifact.path
    assert archived_path.read_text(encoding="utf-8") == "Parsed markdown"


def test_pdf_reparse_uses_stored_original_file(client: TestClient) -> None:
    file_id = _upload_pdf(client, filename="needs-reparse.pdf")
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    assert worker.run_once() is True

    response = client.post(f"/api/pdf/files/{file_id}/reparse")

    assert response.status_code == 202
    task = response.json()
    assert task["file_id"] == file_id
    assert task["status"] == "queued"
    assert task["stage"] == "queued"
    assert task["result"]["operation"] == "reparse"
    assert worker.run_once() is True
    detail_response = client.get(f"/api/pdf/files/{file_id}/detail")
    assert detail_response.status_code == 200
    assert detail_response.json()["parse_report"]["quality_status"] == "good"


def test_pdf_worker_marks_stale_processing_task_with_diagnostics(
    client: TestClient,
    pdf_repository: SQLiteExcelAssetRepository,
) -> None:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", ("stale.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 202
    payload = response.json()
    task_id = payload["tasks"][0]["task_id"]
    file_id = payload["tasks"][0]["file_id"]
    batch_id = payload["batch"]["batch_id"]
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
    assert failed_task.error_message == (
        "PDF processing was interrupted. Please upload the document again."
    )

    failed_file = pdf_repository.get_pdf_file(str(file_id))
    assert failed_file is not None
    assert failed_file.processing_status == PdfProcessingStatus.FAILED
    assert failed_file.status_detail == "PDF parsing failed."
    assert failed_file.error_message == (
        "PDF processing was interrupted. Please upload the document again."
    )

    report = pdf_repository.get_pdf_parse_report(str(file_id))
    assert report is not None
    assert report.quality_status == PdfParseQualityStatus.FAILED
    assert report.warnings == [
        "PDF processing was interrupted. Please upload the document again."
    ]

    batch = pdf_repository.get_pdf_upload_batch(str(batch_id))
    assert batch is not None
    assert batch.status.value == "failed"
    assert batch.error_message == (
        "PDF processing was interrupted. Please upload the document again."
    )
    assert batch.result["failed"] == 1


def _upload_pdf(client: TestClient, filename: str = "safety-standard.pdf") -> str:
    response = client.post(
        "/api/pdf/files/upload-tasks",
        files=[("files", (filename, _pdf_bytes(), "application/pdf"))],
    )
    assert response.status_code == 202
    return str(response.json()["tasks"][0]["file_id"])


def _drain_pdf_upload_batch(client: TestClient, batch_id: str) -> dict[str, object]:
    worker = app.dependency_overrides[get_pdf_upload_task_worker]()
    for _ in range(20):
        batch_response = client.get(f"/api/pdf/files/upload-batches/{batch_id}")
        assert batch_response.status_code == 200
        batch_detail = batch_response.json()
        if batch_detail["batch"]["status"] in {"ready", "partial", "failed", "cancelled"}:
            return batch_detail
        assert worker.run_once() is True
    raise AssertionError("PDF upload batch did not reach a terminal state")


def _find_pdf_file(
    files: list[dict[str, object]],
    *,
    name: str,
    kind: str,
    parent_id: str | None = None,
) -> dict[str, object]:
    for file in files:
        if (
            file["display_name"] == name
            and file["kind"] == kind
            and file["parent_id"] == parent_id
        ):
            return file
    raise AssertionError(f"PDF file entry was not found: {parent_id=}, {kind=}, {name=}")


class FailingPdfParser:
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        raise RuntimeError("parser exploded")


class FailingSummaryLlmClient(FakeLlmClient):
    def generate_document_summary(self, *args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("summary llm failed")


class RecordingPdfLlmClient(FakeLlmClient):
    def __init__(self) -> None:
        self.summary_calls: list[dict[str, str | None]] = []
        self.route_calls: list[dict[str, str | None]] = []
        self.answer_calls: list[dict[str, str | None]] = []

    def generate_document_summary(self, *args, **kwargs):
        self.summary_calls.append(
            {
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
            }
        )
        return super().generate_document_summary(*args, **kwargs)

    def route_documents(self, *args, **kwargs):
        self.route_calls.append(
            {
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
            }
        )
        return super().route_documents(*args, **kwargs)

    def answer_with_pdf_chunks(self, *args, **kwargs):
        self.answer_calls.append(
            {
                "provider": kwargs.get("provider"),
                "model": kwargs.get("model"),
            }
        )
        return super().answer_with_pdf_chunks(*args, **kwargs)


class RoutingProbePdfLlmClient(FakeLlmClient):
    def __init__(self, routes: dict[str, list[str]]) -> None:
        self._routes = routes
        self.route_requests: list[dict[str, object]] = []
        self.answer_requests: list[dict[str, object]] = []

    def route_documents(
        self,
        question,
        summaries,
        max_documents,
        user_questions=None,
        attached_documents=None,
        previous_turns=None,
        **kwargs,
    ):
        _ = user_questions, attached_documents, kwargs
        self.route_requests.append(
            {
                "question": question,
                "candidate_file_ids": [summary.file_id for summary in summaries],
                "duplicate_content_groups": [
                    next(
                        iter(
                            summary.coverage_scope.get(
                                "duplicate_content_group",
                                [],
                            )
                        ),
                        None,
                    )
                    for summary in summaries
                ],
                "max_documents": max_documents,
                "previous_questions": [turn.question for turn in previous_turns or []],
            }
        )
        return [
            SelectedDocument(
                file_id=file_id,
                version_id=file_id,
                reason="selected by routing probe",
                confidence=1.0,
            )
            for file_id in self._routes.get(question, [])
        ]

    def answer_with_pdf_chunks(
        self,
        question,
        chunks,
        previous_turns=None,
        **kwargs,
    ):
        self.answer_requests.append(
            {
                "question": question,
                "chunk_file_ids": [chunk["file_id"] for chunk in chunks],
                "previous_questions": [
                    turn.question for turn in previous_turns or []
                ],
                "previous_answers": [
                    turn.answer_text for turn in previous_turns or []
                ],
                "previous_citation_ids": [
                    turn.citation_ids for turn in previous_turns or []
                ],
                "previous_selected_file_ids": [
                    [
                        document.file_id
                        for document in turn.selected_documents
                    ]
                    for turn in previous_turns or []
                ],
            }
        )
        return super().answer_with_pdf_chunks(
            question,
            chunks,
            previous_turns=previous_turns,
            **kwargs,
        )


class ContextRecordingPdfLlmClient(RoutingProbePdfLlmClient):
    def __init__(self, routes: dict[str, list[str]]) -> None:
        super().__init__(routes)
        self.answer_chunk_file_ids: list[str] = []

    def answer_with_pdf_chunks(self, question, chunks, **kwargs):
        self.answer_chunk_file_ids = [str(chunk["file_id"]) for chunk in chunks]
        return super().answer_with_pdf_chunks(question, chunks, **kwargs)


class VisibilityHidingPdfLlmClient(FakeLlmClient):
    def __init__(
        self,
        *,
        repository: SQLiteExcelAssetRepository,
        file_id: str,
    ) -> None:
        self._repository = repository
        self._file_id = file_id
        self.answer_calls = 0

    def answer_with_pdf_chunks(self, *args, **kwargs):
        answer = super().answer_with_pdf_chunks(*args, **kwargs)
        self.answer_calls += 1
        file = self._repository.get_pdf_file(self._file_id)
        assert file is not None
        self._repository.update_pdf_file_visibility(
            file_id=self._file_id,
            visibility=PdfFileVisibility.HIDDEN,
            updated_at=file.updated_at,
        )
        return answer


class PartialPdfParser:
    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        return ParsedPdfDocument(
            page_count=2,
            chunk_count=1,
            chunks=[
                ParsedPdfChunk(
                    text="Clause 4.1 requires traceable compliance evidence.",
                    page_label="Page 1",
                    title="Clause 4.1",
                    metadata={"source": "partial-test"},
                )
            ],
            pages=[
                ParsedPdfPage(
                    page_number=1,
                    page_label="Page 1",
                    status=PdfParsePageStatus.PARSED,
                    text_block_count=1,
                    char_count=52,
                ),
                ParsedPdfPage(
                    page_number=2,
                    page_label="Page 2",
                    status=PdfParsePageStatus.FAILED,
                    error_message="OCR failed on page 2.",
                ),
            ],
            warnings=["Page 2 failed OCR extraction."],
            artifacts=[
                ParsedPdfArtifact(
                    artifact_type="md",
                    name="partial.md",
                    path="partial.md",
                    size_bytes=128,
                    content_hash="abc123",
                )
            ],
            parser_backend="partial-test",
            quality_status=PdfParseQualityStatus.PARTIAL,
        )


class ArtifactPdfParser:
    def __init__(self, *, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def parse(self, *, filename: str, content: bytes) -> ParsedPdfDocument:
        return ParsedPdfDocument(
            page_count=1,
            chunk_count=1,
            chunks=[
                ParsedPdfChunk(
                    text="Parsed markdown",
                    page_label="Page 1",
                    title="Parsed markdown",
                    metadata={"source": "artifact-test"},
                )
            ],
            pages=[
                ParsedPdfPage(
                    page_number=1,
                    page_label="Page 1",
                    status=PdfParsePageStatus.PARSED,
                    text_block_count=1,
                    char_count=15,
                )
            ],
            artifacts=[
                ParsedPdfArtifact(
                    artifact_type="md",
                    name="document.md",
                    path="document.md",
                    size_bytes=15,
                    content_hash="abc123",
                )
            ],
            artifact_root=self._artifact_root.as_posix(),
            parser_backend="artifact-test",
            quality_status=PdfParseQualityStatus.GOOD,
        )


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
