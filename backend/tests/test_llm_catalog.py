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
    VOLCENGINE_ARK_LLM_MODELS,
    VOLCENGINE_ARK_PROVIDER,
    list_supported_llm_provider_options,
    llm_provider_label,
    supports_deep_thinking,
    supports_json_response_format,
    thinking_request_style,
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


def test_volcengine_ark_provider_exposes_mainstream_models() -> None:
    options = {
        option["provider"]: option
        for option in list_supported_llm_provider_options()
    }

    assert options[VOLCENGINE_ARK_PROVIDER]["label"] == "Volcengine Ark"
    assert options[VOLCENGINE_ARK_PROVIDER]["models"] == list(VOLCENGINE_ARK_LLM_MODELS)
    assert "doubao-seed-2-0-pro-260215" in options[VOLCENGINE_ARK_PROVIDER]["models"]
    assert "doubao-seed-2-0-lite-260428" in options[VOLCENGINE_ARK_PROVIDER]["models"]
    assert "deepseek-v4-pro-260425" in options[VOLCENGINE_ARK_PROVIDER]["models"]
    assert options[VOLCENGINE_ARK_PROVIDER]["deep_thinking_models"] == []


def test_provider_labels_are_centralized() -> None:
    assert llm_provider_label(SILICONFLOW_PROVIDER) == "SiliconFlow"
    assert llm_provider_label(DEEPSEEK_PROVIDER) == "DeepSeek Official"
    assert llm_provider_label(VOLCENGINE_ARK_PROVIDER) == "Volcengine Ark"
    assert llm_provider_label("custom_provider") == "custom_provider"


def test_provider_options_expose_deep_thinking_capabilities() -> None:
    options = {
        option["provider"]: option
        for option in list_supported_llm_provider_options()
    }

    assert options[SILICONFLOW_PROVIDER]["deep_thinking_models"] == [
        "Pro/deepseek-ai/DeepSeek-V3.2",
    ]
    assert options[DEEPSEEK_PROVIDER]["deep_thinking_models"] == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ]
    assert supports_deep_thinking(SILICONFLOW_PROVIDER, "Pro/deepseek-ai/DeepSeek-V3.2")
    assert not supports_deep_thinking(SILICONFLOW_PROVIDER, "Qwen/Qwen3.6-27B")


def test_provider_request_capabilities_are_explicit() -> None:
    assert supports_json_response_format(DEEPSEEK_PROVIDER)
    assert not supports_json_response_format(SILICONFLOW_PROVIDER)
    assert not supports_json_response_format(VOLCENGINE_ARK_PROVIDER)

    assert (
        thinking_request_style(SILICONFLOW_PROVIDER, "Pro/deepseek-ai/DeepSeek-V3.2")
        == "siliconflow_enable_thinking"
    )
    assert thinking_request_style(DEEPSEEK_PROVIDER, "deepseek-v4-pro") == "deepseek_thinking"
    assert thinking_request_style(VOLCENGINE_ARK_PROVIDER, "deepseek-v4-pro-260425") is None
    assert thinking_request_style(SILICONFLOW_PROVIDER, "Qwen/Qwen3.6-27B") is None
