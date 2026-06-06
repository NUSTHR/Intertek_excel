from app.core.llm_catalog import (
    DEFAULT_ANSWER_MODEL,
    DEFAULT_ROUTER_MODEL,
    DEFAULT_SUMMARY_MODEL,
    SILICONFLOW_LLM_MODELS,
    list_supported_llm_provider_options,
)


def test_ling_flash_is_first_siliconflow_default_for_all_chain_stages() -> None:
    expected_model = "inclusionAI/Ling-flash-2.0"

    assert SILICONFLOW_LLM_MODELS[0] == expected_model
    assert DEFAULT_SUMMARY_MODEL == expected_model
    assert DEFAULT_ROUTER_MODEL == expected_model
    assert DEFAULT_ANSWER_MODEL == expected_model
    assert list_supported_llm_provider_options()[0]["models"][0] == expected_model
