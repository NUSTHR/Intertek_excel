import sqlite3
from collections.abc import Callable

from app.domain.models import LlmPreference


class SQLiteLlmPreferenceRepository:
    """Persistence boundary for workspace-level model preferences."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect

    def get(self, scope: str) -> LlmPreference | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM llm_preferences WHERE scope = ?",
                (scope,),
            ).fetchone()
        return _to_llm_preference(row)

    def save(self, preference: LlmPreference) -> LlmPreference:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_preferences
                  (
                    scope, summary_provider, summary_model, router_provider,
                    router_model, answer_provider, answer_model, created_at, updated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                  summary_provider = excluded.summary_provider,
                  summary_model = excluded.summary_model,
                  router_provider = excluded.router_provider,
                  router_model = excluded.router_model,
                  answer_provider = excluded.answer_provider,
                  answer_model = excluded.answer_model,
                  updated_at = excluded.updated_at
                """,
                (
                    preference.scope,
                    preference.summary_provider,
                    preference.summary_model,
                    preference.router_provider,
                    preference.router_model,
                    preference.answer_provider,
                    preference.answer_model,
                    preference.created_at,
                    preference.updated_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM llm_preferences WHERE scope = ?",
                (preference.scope,),
            ).fetchone()
        saved = _to_llm_preference(row)
        if saved is None:
            raise RuntimeError("failed to persist llm preference")
        return saved


def _to_llm_preference(row: sqlite3.Row | None) -> LlmPreference | None:
    if row is None:
        return None
    return LlmPreference(
        scope=str(row["scope"]),
        summary_provider=str(row["summary_provider"]),
        summary_model=str(row["summary_model"]),
        router_provider=str(row["router_provider"]),
        router_model=str(row["router_model"]),
        answer_provider=str(row["answer_provider"]),
        answer_model=str(row["answer_model"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
