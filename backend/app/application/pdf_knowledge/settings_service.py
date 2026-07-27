from app.application.pdf_knowledge.model_settings import (
    default_pdf_model_settings,
    normalized_pdf_model_setting,
    sort_pdf_model_settings,
)
from app.core.errors import AssetNotFoundError, InvalidLlmModelError
from app.core.llm_catalog import (
    is_supported_llm_model_for_provider,
    is_supported_llm_provider,
    normalize_llm_provider,
)
from app.core.time import utc_now_iso
from app.domain.models import PdfModelSetting
from app.ports.repository import PdfKnowledgeRepository


class PdfModelSettingsService:
    """Owns persisted provider/model choices for PDF processing stages."""

    def __init__(self, *, repository: PdfKnowledgeRepository) -> None:
        self._repository = repository

    def list_settings(self) -> list[PdfModelSetting]:
        settings = self._repository.list_pdf_model_settings()
        if settings:
            now = utc_now_iso()
            normalized_settings = [
                normalized_pdf_model_setting(setting, now)
                for setting in settings
            ]
            if normalized_settings != settings:
                normalized_settings = [
                    self._repository.save_pdf_model_setting(setting)
                    for setting in normalized_settings
                ]
            return sort_pdf_model_settings(normalized_settings)
        now = utc_now_iso()
        return [
            self._repository.save_pdf_model_setting(setting)
            for setting in default_pdf_model_settings(now)
        ]

    def update_setting(
        self,
        *,
        setting_id: str,
        selected_provider: str,
        selected_model: str,
    ) -> list[PdfModelSetting]:
        settings = {setting.setting_id: setting for setting in self.list_settings()}
        current = settings.get(setting_id)
        if current is None:
            raise AssetNotFoundError("PDF model setting was not found")
        provider = normalize_llm_provider(selected_provider)
        if not is_supported_llm_provider(provider):
            raise InvalidLlmModelError(
                stage=setting_id,
                model=f"{selected_provider}:{selected_model}",
            )
        if not is_supported_llm_model_for_provider(provider, selected_model):
            raise InvalidLlmModelError(
                stage=setting_id,
                model=f"{provider}:{selected_model}",
            )
        self._repository.save_pdf_model_setting(
            PdfModelSetting(
                setting_id=current.setting_id,
                label=current.label,
                providers=current.providers,
                models=current.models,
                selected_provider=provider,
                selected_model=selected_model,
                created_at=current.created_at,
                updated_at=utc_now_iso(),
            )
        )
        return self.list_settings()
