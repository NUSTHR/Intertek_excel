from collections.abc import Iterable
from typing import Literal

ThinkingRequestStyle = Literal["siliconflow_enable_thinking", "deepseek_thinking"]

SILICONFLOW_PROVIDER = "siliconflow"
DEEPSEEK_PROVIDER = "deepseek"
VOLCENGINE_ARK_PROVIDER = "volcengine_ark"

SUPPORTED_LLM_PROVIDERS: tuple[str, ...] = (
    SILICONFLOW_PROVIDER,
    DEEPSEEK_PROVIDER,
    VOLCENGINE_ARK_PROVIDER,
)

LLM_PROVIDER_LABELS: dict[str, str] = {
    SILICONFLOW_PROVIDER: "SiliconFlow",
    DEEPSEEK_PROVIDER: "DeepSeek Official",
    VOLCENGINE_ARK_PROVIDER: "Volcengine Ark",
}

SILICONFLOW_LLM_MODELS: tuple[str, ...] = (
    "inclusionAI/Ling-flash-2.0",
    "deepseek-ai/DeepSeek-V4-Pro",
    "Pro/deepseek-ai/DeepSeek-V3.2",
    "Qwen/Qwen3.6-27B",
    "Qwen/Qwen3.6-35B-A3B",
)

DEEPSEEK_OFFICIAL_LLM_MODELS: tuple[str, ...] = (
    "deepseek-v4-pro",
    "deepseek-v4-flash",
)

VOLCENGINE_ARK_LLM_MODELS: tuple[str, ...] = (
    "doubao-seed-2-0-pro-260215",
    "doubao-seed-2-0-lite-260428",
    "doubao-seed-2-0-mini-260428",
    "doubao-seed-2-0-lite-260215",
    "doubao-seed-1-8-251228",
    "deepseek-v4-pro-260425",
    "deepseek-v4-flash-260425",
    "deepseek-v3.2",
)

SUPPORTED_LLM_MODELS_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    SILICONFLOW_PROVIDER: SILICONFLOW_LLM_MODELS,
    DEEPSEEK_PROVIDER: DEEPSEEK_OFFICIAL_LLM_MODELS,
    VOLCENGINE_ARK_PROVIDER: VOLCENGINE_ARK_LLM_MODELS,
}

SUPPORTED_LLM_MODELS: tuple[str, ...] = tuple(
    dict.fromkeys(
        [
            *SILICONFLOW_LLM_MODELS,
            *DEEPSEEK_OFFICIAL_LLM_MODELS,
            *VOLCENGINE_ARK_LLM_MODELS,
        ]
    )
)

DEFAULT_SUMMARY_PROVIDER = DEEPSEEK_PROVIDER
DEFAULT_ROUTER_PROVIDER = SILICONFLOW_PROVIDER
DEFAULT_ANSWER_PROVIDER = DEEPSEEK_PROVIDER
DEFAULT_SUMMARY_MODEL = "deepseek-v4-pro"
DEFAULT_ROUTER_MODEL = "Qwen/Qwen3.6-35B-A3B"
DEFAULT_ANSWER_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_SUMMARY_MODEL = "deepseek-v4-pro"
DEFAULT_DEEPSEEK_ROUTER_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_ANSWER_MODEL = "deepseek-v4-pro"
DEFAULT_VOLCENGINE_ARK_SUMMARY_MODEL = "doubao-seed-2-0-pro-260215"
DEFAULT_VOLCENGINE_ARK_ROUTER_MODEL = "doubao-seed-2-0-lite-260428"
DEFAULT_VOLCENGINE_ARK_ANSWER_MODEL = "deepseek-v4-pro-260425"

DEEP_THINKING_MODELS_BY_PROVIDER: dict[str, tuple[str, ...]] = {
    SILICONFLOW_PROVIDER: (
        "Pro/deepseek-ai/DeepSeek-V3.2",
    ),
    DEEPSEEK_PROVIDER: DEEPSEEK_OFFICIAL_LLM_MODELS,
}

JSON_RESPONSE_FORMAT_PROVIDERS: tuple[str, ...] = (
    DEEPSEEK_PROVIDER,
)

THINKING_REQUEST_STYLE_BY_PROVIDER: dict[str, ThinkingRequestStyle] = {
    SILICONFLOW_PROVIDER: "siliconflow_enable_thinking",
    DEEPSEEK_PROVIDER: "deepseek_thinking",
}


def is_supported_llm_model(model: str) -> bool:
    return model in SUPPORTED_LLM_MODELS


def is_supported_llm_provider(provider: str) -> bool:
    return normalize_llm_provider(provider) in SUPPORTED_LLM_PROVIDERS


def is_supported_llm_model_for_provider(provider: str, model: str) -> bool:
    return model in SUPPORTED_LLM_MODELS_BY_PROVIDER.get(
        normalize_llm_provider(provider),
        (),
    )


def normalize_llm_provider(provider: str) -> str:
    return provider.strip().lower()


def llm_provider_label(provider: str) -> str:
    provider_id = normalize_llm_provider(provider)
    return LLM_PROVIDER_LABELS.get(provider_id, provider_id)


def supports_deep_thinking(provider: str, model: str) -> bool:
    return model in DEEP_THINKING_MODELS_BY_PROVIDER.get(
        normalize_llm_provider(provider),
        (),
    )


def supports_json_response_format(provider: str) -> bool:
    return normalize_llm_provider(provider) in JSON_RESPONSE_FORMAT_PROVIDERS


def thinking_request_style(provider: str, model: str) -> ThinkingRequestStyle | None:
    provider_id = normalize_llm_provider(provider)
    if not supports_deep_thinking(provider_id, model):
        return None
    return THINKING_REQUEST_STYLE_BY_PROVIDER.get(provider_id)


def list_deep_thinking_models(provider: str) -> list[str]:
    return list(DEEP_THINKING_MODELS_BY_PROVIDER.get(normalize_llm_provider(provider), ()))


def list_supported_llm_models(provider: str | None = None) -> list[str]:
    if provider is None:
        return list(SUPPORTED_LLM_MODELS)
    return list(SUPPORTED_LLM_MODELS_BY_PROVIDER.get(normalize_llm_provider(provider), ()))


def list_supported_llm_provider_options() -> list[dict[str, object]]:
    return [
        {
            "provider": provider,
            "label": LLM_PROVIDER_LABELS[provider],
            "models": list(SUPPORTED_LLM_MODELS_BY_PROVIDER[provider]),
            "deep_thinking_models": list_deep_thinking_models(provider),
        }
        for provider in SUPPORTED_LLM_PROVIDERS
    ]


def unique_supported_models(models: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for model in models:
        if model not in seen and model in SUPPORTED_LLM_MODELS:
            seen.add(model)
            ordered.append(model)
    return ordered
