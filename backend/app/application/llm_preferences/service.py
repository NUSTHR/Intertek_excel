from app.core.config import Settings
from app.core.time import utc_now_iso
from app.domain.models import LlmPreference
from app.ports.repository import LlmPreferenceRepository

WORKSPACE_PREFERENCE_SCOPE = "workspace"


class WorkspaceLlmPreferenceService:
    def __init__(
        self,
        repository: LlmPreferenceRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    def get_preference(self) -> LlmPreference:
        preference = self._repository.get_llm_preference(WORKSPACE_PREFERENCE_SCOPE)
        if preference is not None:
            return preference
        return self._default_preference()

    def save_preference(
        self,
        *,
        summary_provider: str,
        summary_model: str,
        router_provider: str,
        router_model: str,
        answer_provider: str,
        answer_model: str,
    ) -> LlmPreference:
        existing = self._repository.get_llm_preference(WORKSPACE_PREFERENCE_SCOPE)
        now = utc_now_iso()
        return self._repository.save_llm_preference(
            LlmPreference(
                scope=WORKSPACE_PREFERENCE_SCOPE,
                summary_provider=summary_provider,
                summary_model=summary_model,
                router_provider=router_provider,
                router_model=router_model,
                answer_provider=answer_provider,
                answer_model=answer_model,
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
        )

    def _default_preference(self) -> LlmPreference:
        return LlmPreference(
            scope=WORKSPACE_PREFERENCE_SCOPE,
            summary_provider=self._settings.llm_summary_provider,
            summary_model=self._settings.llm_summary_model,
            router_provider=self._settings.llm_router_provider,
            router_model=self._settings.llm_router_model,
            answer_provider=self._settings.llm_answer_provider,
            answer_model=self._settings.llm_answer_model,
            created_at="",
            updated_at="",
        )
