from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import workspace
from app.main import app


def test_workspace_config_exposes_upload_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        workspace,
        "get_settings",
        lambda: SimpleNamespace(
            excel_max_upload_bytes=1234,
            supported_excel_extensions=(".xlsx", ".xlsm"),
        ),
    )

    with TestClient(app) as client:
        response = client.get("/api/workspace/config")

    assert response.status_code == 200
    assert response.json() == {
        "upload": {
            "max_bytes": 1234,
            "supported_extensions": [".xlsx", ".xlsm"],
        }
    }
