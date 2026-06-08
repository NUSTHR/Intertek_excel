from app.core.llm_catalog import (
    DEEPSEEK_PROVIDER,
    DEFAULT_ANSWER_MODEL,
    DEFAULT_ANSWER_PROVIDER,
    DEFAULT_ROUTER_MODEL,
    DEFAULT_ROUTER_PROVIDER,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_SUMMARY_PROVIDER,
    SILICONFLOW_LLM_MODELS,
    SILICONFLOW_PROVIDER,
    list_supported_llm_provider_options,
)


def test_stage_defaults_match_business_model_policy() -> None:
    assert DEFAULT_SUMMARY_PROVIDER == DEEPSEEK_PROVIDER
    assert DEFAULT_SUMMARY_MODEL == "deepseek-v4-pro"
    assert DEFAULT_ROUTER_PROVIDER == SILICONFLOW_PROVIDER
    assert DEFAULT_ROUTER_MODEL == "Qwen/Qwen3.6-35B-A3B"
    assert DEFAULT_ANSWER_PROVIDER == DEEPSEEK_PROVIDER
    assert DEFAULT_ANSWER_MODEL == "deepseek-v4-pro"


def test_siliconflow_provider_still_lists_ling_flash_first() -> None:
    assert SILICONFLOW_LLM_MODELS[0] == "inclusionAI/Ling-flash-2.0"
    assert list_supported_llm_provider_options()[0]["models"][0] == "inclusionAI/Ling-flash-2.0"
