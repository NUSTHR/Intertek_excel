from dataclasses import dataclass

from app.core.llm_catalog import (
    DEFAULT_ANSWER_MODEL,
    DEFAULT_ANSWER_PROVIDER,
    DEFAULT_ROUTER_MODEL,
    DEFAULT_ROUTER_PROVIDER,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_SUMMARY_PROVIDER,
    list_supported_llm_models,
    list_supported_llm_provider_options,
)
from app.domain.models import PdfModelSetting

PDF_MODEL_SETTING_STAGES = (
    ("summary", "Summary Engine"),
    ("router", "Router Engine"),
    ("chat", "Chat Engine"),
)
PDF_MODEL_SETTING_ORDER = {
    setting_id: index
    for index, (setting_id, _label) in enumerate(PDF_MODEL_SETTING_STAGES)
}
PDF_DEFAULT_STAGE_SELECTIONS = {
    "summary": (DEFAULT_SUMMARY_PROVIDER, DEFAULT_SUMMARY_MODEL),
    "router": (DEFAULT_ROUTER_PROVIDER, DEFAULT_ROUTER_MODEL),
    "chat": (DEFAULT_ANSWER_PROVIDER, DEFAULT_ANSWER_MODEL),
}


@dataclass(frozen=True)
class PdfModelSelection:
    provider: str
    model: str


def default_pdf_model_settings(now: str) -> list[PdfModelSetting]:
    providers = [
        str(option["provider"])
        for option in list_supported_llm_provider_options()
    ]
    models = list_supported_llm_models()
    return [
        PdfModelSetting(
            setting_id=setting_id,
            label=label,
            providers=list(providers),
            models=list(models),
            selected_provider=_default_provider(setting_id),
            selected_model=_default_model(setting_id),
            created_at=now,
            updated_at=now,
        )
        for setting_id, label in PDF_MODEL_SETTING_STAGES
    ]


def sort_pdf_model_settings(settings: list[PdfModelSetting]) -> list[PdfModelSetting]:
    return sorted(
        settings,
        key=lambda setting: PDF_MODEL_SETTING_ORDER.get(setting.setting_id, 999),
    )


def normalized_pdf_model_setting(setting: PdfModelSetting, now: str) -> PdfModelSetting:
    providers = [
        str(option["provider"])
        for option in list_supported_llm_provider_options()
    ]
    models = list_supported_llm_models()
    provider = _normalize_provider_alias(setting.selected_provider)
    model = setting.selected_model
    if provider not in providers or model not in list_supported_llm_models(provider):
        provider = _default_provider(setting.setting_id)
        model = _default_model(setting.setting_id)
    return PdfModelSetting(
        setting_id=setting.setting_id,
        label=setting.label,
        providers=list(providers),
        models=list(models),
        selected_provider=provider,
        selected_model=model,
        created_at=setting.created_at,
        updated_at=(
            now
            if _model_setting_changed(setting, providers, models, provider, model)
            else setting.updated_at
        ),
    )


def pdf_model_selection(
    settings: list[PdfModelSetting],
    setting_id: str,
) -> PdfModelSelection:
    for setting in settings:
        if setting.setting_id == setting_id:
            return PdfModelSelection(
                provider=setting.selected_provider,
                model=setting.selected_model,
            )
    return PdfModelSelection(
        provider=_default_provider(setting_id),
        model=_default_model(setting_id),
    )


def _default_provider(setting_id: str) -> str:
    return PDF_DEFAULT_STAGE_SELECTIONS.get(
        setting_id,
        (DEFAULT_ANSWER_PROVIDER, DEFAULT_ANSWER_MODEL),
    )[0]


def _default_model(setting_id: str) -> str:
    return PDF_DEFAULT_STAGE_SELECTIONS.get(
        setting_id,
        (DEFAULT_ANSWER_PROVIDER, DEFAULT_ANSWER_MODEL),
    )[1]


def _normalize_provider_alias(provider: str) -> str:
    provider_id = provider.strip().lower()
    aliases = {
        "siliconflow": "siliconflow",
        "silicon flow": "siliconflow",
        "deepseek": "deepseek",
        "deepseek official": "deepseek",
        "volcengine ark": "volcengine_ark",
        "volcengine_ark": "volcengine_ark",
    }
    return aliases.get(provider_id, provider_id)


def _model_setting_changed(
    setting: PdfModelSetting,
    providers: list[str],
    models: list[str],
    selected_provider: str,
    selected_model: str,
) -> bool:
    return (
        setting.providers != providers
        or setting.models != models
        or setting.selected_provider != selected_provider
        or setting.selected_model != selected_model
    )
