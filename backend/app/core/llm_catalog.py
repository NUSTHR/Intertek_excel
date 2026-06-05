from collections.abc import Iterable

SUPPORTED_LLM_MODELS: tuple[str, ...] = (
    "deepseek-ai/DeepSeek-V4-Pro",
    "Pro/deepseek-ai/DeepSeek-V3.2",
    "Qwen/Qwen3.6-27B",
    "Qwen/Qwen3.6-35B-A3B",
    "inclusionAI/Ling-flash-2.0",
)

DEFAULT_SUMMARY_MODEL = "deepseek-ai/DeepSeek-V4-Pro"
DEFAULT_ROUTER_MODEL = "inclusionAI/Ling-flash-2.0"
DEFAULT_ANSWER_MODEL = "deepseek-ai/DeepSeek-V4-Pro"

# SiliconFlow's public docs explicitly mention enable_thinking for Qwen3
# families and DeepSeek-V3.2. For Pro/* variants we avoid the parameter and
# let the request proceed without a thinking toggle.
ENABLE_THINKING_FALSE_EXACT_MODELS: frozenset[str] = frozenset(
    {
        "deepseek-ai/DeepSeek-V3.2",
    }
)
ENABLE_THINKING_FALSE_PREFIXES: tuple[str, ...] = (
    "Qwen/Qwen3",
)


def is_supported_llm_model(model: str) -> bool:
    return model in SUPPORTED_LLM_MODELS


def supports_enable_thinking_false(model: str) -> bool:
    if model in ENABLE_THINKING_FALSE_EXACT_MODELS:
        return True
    return any(model.startswith(prefix) for prefix in ENABLE_THINKING_FALSE_PREFIXES)


def list_supported_llm_models() -> list[str]:
    return list(SUPPORTED_LLM_MODELS)


def unique_supported_models(models: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for model in models:
        if model not in seen and model in SUPPORTED_LLM_MODELS:
            seen.add(model)
            ordered.append(model)
    return ordered
