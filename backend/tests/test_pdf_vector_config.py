import pytest

from app.core.config import Settings


def _enabled_settings(**overrides) -> Settings:
    values = {
        "pdf_vector_indexing_enabled": True,
        "pdf_vector_ranking_enabled": True,
        "pdf_embedding_api_base_url": "http://embedding.test/v1",
        "pdf_embedding_revision": "embedding-contract-v1",
        "pdf_reranker_api_base_url": "http://reranker.test/v1",
        "pdf_reranker_revision": "reranker-contract-v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_disabled_vector_search_needs_no_external_configuration() -> None:
    Settings(_env_file=None).validate_runtime_safety()


def test_enabled_vector_search_accepts_pinned_model_revisions() -> None:
    _enabled_settings().validate_runtime_safety()


def test_embedding_and_reranker_inherit_siliconflow_connection() -> None:
    settings = _enabled_settings(
        pdf_embedding_api_base_url="",
        pdf_embedding_api_key="",
        pdf_reranker_api_base_url="",
        pdf_reranker_api_key="",
        llm_api_base_url="https://api.siliconflow.cn/v1",
        llm_api_key="shared-secret",
    )

    assert settings.pdf_embedding_resolved_api_base_url.endswith("/v1")
    assert settings.pdf_embedding_resolved_api_key == "shared-secret"
    assert settings.pdf_reranker_resolved_api_key == "shared-secret"


def test_shadow_indexing_does_not_require_reranker_configuration() -> None:
    _enabled_settings(
        pdf_vector_ranking_enabled=False,
        pdf_reranker_api_base_url="",
        pdf_reranker_revision="",
    ).validate_runtime_safety()


def test_ranking_without_indexing_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="requires PDF_VECTOR_INDEXING_ENABLED"):
        _enabled_settings(pdf_vector_indexing_enabled=False).validate_runtime_safety()


def test_production_rejects_runtime_qdrant_bootstrap() -> None:
    with pytest.raises(RuntimeError, match="PDF_QDRANT_AUTO_BOOTSTRAP"):
        _enabled_settings(
            app_env="production",
            auth_admin_password="strong-password",
            auth_expose_reset_token=False,
            auth_cookie_secure=True,
            app_cors_origins="https://workspace.example.com",
            llm_api_key="shared-secret",
            pdf_qdrant_auto_bootstrap=True,
        ).validate_runtime_safety()


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        (
            {"pdf_embedding_api_base_url": "", "llm_api_base_url": ""},
            "PDF_EMBEDDING_API_BASE_URL",
        ),
        ({"pdf_embedding_revision": ""}, "PDF_EMBEDDING_REVISION is required"),
        ({"pdf_reranker_revision": ""}, "PDF_RERANKER_REVISION is required"),
        ({"pdf_embedding_dimension": 0}, "PDF_EMBEDDING_DIMENSION"),
    ],
)
def test_enabled_vector_search_rejects_unsafe_configuration(
    overrides: dict[str, object],
    expected_message: str,
) -> None:
    with pytest.raises(RuntimeError, match=expected_message):
        _enabled_settings(**overrides).validate_runtime_safety()


def test_answer_context_limits_must_be_positive_even_when_vector_search_is_off() -> None:
    with pytest.raises(RuntimeError, match="PDF_ANSWER_MAX_CONTEXT_TOKENS"):
        Settings(
            _env_file=None,
            pdf_answer_max_context_tokens=0,
        ).validate_runtime_safety()
