import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2

from app.core.errors import ExcelWorkspaceError, InvalidLlmModelError, LlmRequestError
from app.core.ids import new_id
from app.core.llm_catalog import (
    DEEPSEEK_PROVIDER,
    SILICONFLOW_PROVIDER,
    is_supported_llm_model_for_provider,
    is_supported_llm_provider,
    normalize_llm_provider,
    supports_enable_thinking_false,
)
from app.core.time import utc_now_iso
from app.domain.models import (
    AttachedDocument,
    ChatTurn,
    DocumentSummary,
    DraftAnswerBlock,
    DraftChatAnswer,
    DraftCitation,
    SelectedDocument,
    SheetSummary,
    WorkbookProfile,
)

logger = logging.getLogger(__name__)

DOCUMENT_SUMMARY_SYSTEM_PROMPT = "\n".join(
    [
        "You are an enterprise Excel document profiling assistant.",
        "",
        "Your task is to generate a structured metadata summary for one Excel workbook version.",
        "",
        "You will receive only deterministic workbook profile data extracted by the backend:",
        "filename, sheets, candidate headers, row counts, column counts, and sample rows.",
        "",
        "Rules:",
        "1. Use only the provided profile facts.",
        "2. Do not invent rows, columns, business meanings, dates, standards, prices, "
        "or conclusions that are not supported by the profile.",
        "3. The summary is used for document routing, not as a factual answer source.",
        "4. Keep all identifiers exactly as provided, especially file_id, version_id, "
        "sheet_id, and sheet_name.",
        "5. Prefer short, searchable phrases in key_topics.",
        "6. suitable_questions should be natural user questions this workbook is likely able "
        "to help answer.",
        "7. unsuitable_questions should describe questions this workbook likely cannot answer.",
        "8. Return strict JSON only. Do not return markdown, explanation, comments, "
        "or code fences.",
    ]
)

DOCUMENT_ROUTER_SYSTEM_PROMPT = "\n".join(
    [
        "You are a document router for an enterprise Excel question answering system.",
        "",
        "Your job is to choose the Excel workbook versions that should be used as "
        "evidence sources for the current user turn.",
        "",
        "The field document_for_this_turn means exactly this: the documents that should "
        "be used to answer the current user turn. It is not the full session history, "
        "not every attached document, and not every broadly related document.",
        "",
        "Rules:",
        "1. Do not answer the user's question.",
        "2. Select only from the provided document catalog.",
        "3. Use version_id as the primary selection id.",
        "4. Use routing memory only to resolve conversational context, such as follow-up "
        "questions, pronouns, abbreviations, refinements, repeated product context, "
        "or references to previous turns.",
        "5. If the current turn continues the same product, domain, region, regulation type, "
        "standard family, document family, or business topic as recent turns, prefer "
        "recently used attached documents when their catalog metadata remains likely "
        "to contain evidence.",
        "6. If the current turn introduces a new product, domain, region, regulation type, "
        "standard family, document family, or business topic, choose additional candidate "
        "documents only when their catalog metadata indicates likely evidence.",
        "7. Do not keep old attached documents for the current turn just because they were "
        "used earlier. Include them only when they are useful for the current turn.",
        "8. Do not add documents that are merely adjacent, generic, or weakly related.",
        "9. If no catalog document is likely to contain evidence for the current turn, "
        "return an empty document_for_this_turn array.",
        "10. Keep document_for_this_turn as small as possible; only increase it via "
        "controlled recall when a likely evidence source would otherwise be missed.",
        "11. The reason should be short and based on catalog metadata or routing memory.",
        "12. Return strict JSON only. Do not return markdown, explanation, comments, "
        "or code fences.",
        "13. Respond as quickly and concisely as possible while fully satisfying the above "
        "requirements. Avoid any unnecessary elaboration, extra reasoning steps, or verbose "
        "output. Output only the minimal JSON required.",
    ]
)

ANSWER_SYSTEM_PROMPT = """
You are an enterprise Excel answer assistant.

You answer user questions using only the provided Excel rows.

Rules:
1. Use only the provided rows as evidence.
2. Do not use outside knowledge.
3. Every factual claim based on Excel data must cite one or more evidence refs.
4. Citations must reference row_id values from the provided rows only.
5. Do not invent row_id, sheet_id, file_id, version_id, dates, values, or row contents.
6. If the provided rows are insufficient, say so clearly.
7. Keep the answer concise and business-readable.
8. Return strict JSON only. Do not return markdown, comments, explanations, or code fences.
""".strip()


@dataclass(frozen=True)
class SiliconFlowConfig:
    api_base_url: str
    api_key: str
    summary_model: str
    router_model: str
    answer_model: str
    timeout_seconds: float
    summary_max_profile_rows: int


@dataclass(frozen=True)
class LlmProviderConfig:
    provider: str
    label: str
    api_base_url: str
    api_key: str
    summary_model: str
    router_model: str
    answer_model: str


class MultiProviderLlmClient:
    def __init__(
        self,
        config: SiliconFlowConfig,
        post: Callable[..., httpx2.Response] = httpx2.post,
        extra_providers: dict[str, LlmProviderConfig] | None = None,
        default_providers: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._post = post
        self._providers = {
            SILICONFLOW_PROVIDER: LlmProviderConfig(
                provider=SILICONFLOW_PROVIDER,
                label="SiliconFlow",
                api_base_url=config.api_base_url,
                api_key=config.api_key,
                summary_model=config.summary_model,
                router_model=config.router_model,
                answer_model=config.answer_model,
            ),
            **(extra_providers or {}),
        }
        self._default_providers = {
            "summary": SILICONFLOW_PROVIDER,
            "router": SILICONFLOW_PROVIDER,
            "answer": SILICONFLOW_PROVIDER,
            **(default_providers or {}),
        }

    def generate_document_summary(
        self,
        profile: WorkbookProfile,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> DocumentSummary:
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="summary",
        )
        payload = self._chat_json(
            stage="document_summary_model",
            provider_config=provider_config,
            model=resolved_model,
            system_prompt=DOCUMENT_SUMMARY_SYSTEM_PROMPT,
            user_prompt=(
                "Generate a structured document summary for this Excel workbook profile.\n\n"
                "Return JSON in exactly this shape:\n\n"
                "{\n"
                '  "summary_text": "string",\n'
                '  "business_domain": "string",\n'
                '  "key_topics": ["string"],\n'
                '  "suitable_questions": ["string"],\n'
                '  "unsuitable_questions": ["string"],\n'
                '  "sheet_summaries": [\n'
                "    {\n"
                '      "sheet_id": "string",\n'
                '      "sheet_name": "string",\n'
                '      "summary": "string",\n'
                '      "important_columns": ["string"],\n'
                '      "likely_question_types": ["string"]\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "Workbook profile:\n"
                f"{json.dumps(self._profile_payload(profile), ensure_ascii=False)}"
            ),
        )
        allowed_sheet_ids = {sheet.sheet_id for sheet in profile.sheets}
        return DocumentSummary(
            summary_id=new_id("summary"),
            file_id=profile.file_id,
            version_id=profile.version_id,
            summary_text=str(payload.get("summary_text", "")).strip()
            or f"{profile.original_filename} contains {len(profile.sheets)} sheet(s).",
            business_domain=str(payload.get("business_domain", "excel workbook")).strip()
            or "excel workbook",
            key_topics=self._string_list(payload.get("key_topics")),
            suitable_questions=self._string_list(payload.get("suitable_questions")),
            unsuitable_questions=self._string_list(payload.get("unsuitable_questions")),
            sheet_summaries=[
                SheetSummary(
                    sheet_id=str(sheet.get("sheet_id", "")),
                    sheet_name=str(sheet.get("sheet_name", "")),
                    summary=str(sheet.get("summary", "")),
                    important_columns=self._string_list(sheet.get("important_columns")),
                    likely_question_types=self._string_list(sheet.get("likely_question_types")),
                )
                for sheet in self._object_list(payload.get("sheet_summaries"))
                if str(sheet.get("sheet_id", "")) in allowed_sheet_ids
            ],
            created_at=utc_now_iso(),
        )

    def route_documents(
        self,
        question: str,
        summaries: list[DocumentSummary],
        max_documents: int,
        user_questions: list[str] | None = None,
        attached_documents: list[AttachedDocument] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> list[SelectedDocument]:
        if not summaries:
            return []
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="router",
        )
        _ = user_questions
        document_catalog_json = json.dumps(
            self._routing_document_catalog(
                summaries=summaries,
                attached_documents=attached_documents or [],
                previous_turns=previous_turns or [],
            ),
            ensure_ascii=False,
        )
        payload = self._chat_json(
            stage="route_model",
            provider_config=provider_config,
            model=resolved_model,
            messages=[
                {"role": "system", "content": DOCUMENT_ROUTER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Document catalog for routing. Each item is one selectable "
                        "workbook version.\n\n"
                        f"{document_catalog_json}"
                    ),
                },
                *self._routing_memory_messages(previous_turns or []),
                {
                    "role": "user",
                    "content": (
                        "Route the current user turn.\n\n"
                        f"Maximum documents for this turn: {max_documents}\n\n"
                        "Current question:\n"
                        f"{question}\n\n"
                        "Return JSON in exactly this shape:\n\n"
                        "{\n"
                        '  "routing_decision": '
                        '"reuse_attached | attach_incrementally | no_match",\n'
                        '  "document_for_this_turn": [\n'
                        "    {\n"
                        '      "file_id": "string",\n'
                        '      "version_id": "string",\n'
                        '      "reason": "string",\n'
                        '      "confidence": 0.0\n'
                        "    }\n"
                        "  ],\n"
                        '  "decision_reason": "string",\n'
                        '  "no_match_reason": "string"\n'
                        "}"
                    ),
                },
            ],
        )
        selected = [
            SelectedDocument(
                file_id=str(item.get("file_id", "")),
                version_id=str(item.get("version_id", "")),
                reason=str(item.get("reason", "")),
                confidence=self._optional_float(item.get("confidence")),
            )
            for item in self._object_list(
                payload.get("document_for_this_turn", payload.get("selected_documents"))
            )
        ]
        allowed = {summary.version_id: summary.file_id for summary in summaries}
        unique_selected: list[SelectedDocument] = []
        seen_version_ids: set[str] = set()
        for document in selected:
            if allowed.get(document.version_id) != document.file_id:
                continue
            if document.version_id in seen_version_ids:
                continue
            seen_version_ids.add(document.version_id)
            unique_selected.append(document)
        return unique_selected

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> DraftChatAnswer:
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="answer",
        )
        documents_json = json.dumps(
            [document.__dict__ for document in documents],
            ensure_ascii=False,
        )
        rows_json = json.dumps(rows, ensure_ascii=False)
        logger.debug(
            "preparing answer model payload document_count=%s row_count=%s "
            "previous_turn_count=%s selected_version_ids=%s",
            len(documents),
            len(rows),
            len(previous_turns or []),
            [document.version_id for document in documents],
        )
        payload = self._chat_json(
            stage="answer_model",
            provider_config=provider_config,
            model=resolved_model,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                *self._history_messages(previous_turns or []),
                {
                    "role": "user",
                    "content": (
                        "Answer the question using the provided Excel rows.\n\n"
                        f"Question:\n{question}\n\n"
                        f"Selected documents:\n{documents_json}\n\n"
                        f"Rows:\n{rows_json}\n\n"
                        "Each row object has file_id, version_id, sheet_id, sheet_name, "
                        "row_id, cells.\n\n"
                        "Return JSON in exactly this shape:\n\n"
                        "{\n"
                        '  "answer_blocks": [\n'
                        "    {\n"
                        '      "text": "string",\n'
                        '      "evidence_row_ids": ["string"]\n'
                        "    }\n"
                        "  ],\n"
                        '  "citations": [\n'
                        "    {\n"
                        '      "row_id": "string",\n'
                        '      "quote": "string"\n'
                        "    }\n"
                        "  ],\n"
                        '  "insufficient_evidence": false,\n'
                        '  "follow_up_suggestions": ["string"]\n'
                        "}\n\n"
                        "Important:\n"
                        "- evidence_row_ids must contain only row_id values from Rows.\n"
                        "- citations must contain only row_id values from Rows.\n"
                        "- quote should be a short snippet copied or summarized from the "
                        "cited row.\n"
                        "- If no provided row supports an answer, set insufficient_evidence "
                        "to true and return empty citations."
                    ),
                },
            ],
        )
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=str(block.get("text", "")).strip(),
                    evidence_row_ids=self._string_list(block.get("evidence_row_ids")),
                )
                for block in self._object_list(payload.get("answer_blocks"))
                if str(block.get("text", "")).strip()
            ],
            citations=[
                DraftCitation(
                    row_id=str(citation.get("row_id", "")).strip(),
                    quote=str(citation.get("quote", "")).strip(),
                )
                for citation in self._object_list(payload.get("citations"))
                if str(citation.get("row_id", "")).strip()
            ],
            insufficient_evidence=bool(payload.get("insufficient_evidence", False)),
            follow_up_suggestions=self._string_list(payload.get("follow_up_suggestions")),
        )

    def _chat_json(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        content = self._chat_text(
            stage=stage,
            provider_config=provider_config,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
        )
        return self._parse_json_object(content)

    def _chat_text(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        if not provider_config.api_key.strip():
            raise ExcelWorkspaceError(f"{provider_config.label} API key is required for LLM calls")

        url = f"{provider_config.api_base_url.rstrip('/')}/chat/completions"
        request_payload = {
            "model": model,
            "messages": self._request_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages,
            ),
            "temperature": 0.2,
        }
        provider_options = self._provider_request_options(provider_config.provider, model)
        request_payload.update(provider_options)
        logger.debug(
            "sending llm request stage=%s provider=%s model=%s url=%s request_keys=%s",
            stage,
            provider_config.provider,
            model,
            url,
            sorted(request_payload.keys()),
        )
        started_at = perf_counter()
        try:
            response = self._post(
                url,
                headers={
                    "Authorization": f"Bearer {provider_config.api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx2.HTTPError as exc:
            response = getattr(exc, "response", None)
            response_text = ""
            status_code = None
            if response is not None:
                status_code = response.status_code
                try:
                    response_text = response.text
                except Exception:
                    response_text = "<unavailable>"
            logger.debug(
                "llm request failed stage=%s provider=%s model=%s status_code=%s "
                "duration_seconds=%.6f response_text_preview=%s provider_options=%s",
                stage,
                provider_config.provider,
                model,
                status_code,
                perf_counter() - started_at,
                response_text[:2000],
                provider_options,
            )
            raise LlmRequestError(
                stage=stage,
                model=model,
                duration_seconds=perf_counter() - started_at,
                cause=exc,
            ) from exc
        logger.debug(
            "llm request succeeded stage=%s provider=%s model=%s status_code=%s "
            "duration_seconds=%.6f",
            stage,
            provider_config.provider,
            model,
            response.status_code,
            perf_counter() - started_at,
        )
        payload = response.json()
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ExcelWorkspaceError("LLM response did not include message content") from exc

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExcelWorkspaceError("LLM response was not valid JSON") from exc
        if not isinstance(value, dict):
            raise ExcelWorkspaceError("LLM response JSON must be an object")
        return value

    def _profile_payload(self, profile: WorkbookProfile) -> dict[str, Any]:
        return {
            "file_id": profile.file_id,
            "version_id": profile.version_id,
            "original_filename": profile.original_filename,
            "sheets": [
                {
                    "sheet_id": sheet.sheet_id,
                    "sheet_code": sheet.sheet_code,
                    "sheet_name": sheet.sheet_name,
                    "row_count": sheet.row_count,
                    "column_count": sheet.column_count,
                    "candidate_header": sheet.candidate_header,
                    "sample_rows": sheet.sample_rows[: self._config.summary_max_profile_rows],
                }
                for sheet in profile.sheets
            ],
        }

    def _summary_payload(self, summary: DocumentSummary) -> dict[str, Any]:
        return {
            "file_id": summary.file_id,
            "version_id": summary.version_id,
            "summary_text": summary.summary_text,
            "business_domain": summary.business_domain,
            "key_topics": summary.key_topics,
            "suitable_questions": summary.suitable_questions,
            "unsuitable_questions": summary.unsuitable_questions,
            "sheet_summaries": [sheet.__dict__ for sheet in summary.sheet_summaries],
        }

    def _routing_document_catalog(
        self,
        *,
        summaries: list[DocumentSummary],
        attached_documents: list[AttachedDocument],
        previous_turns: list[ChatTurn],
    ) -> list[dict[str, Any]]:
        attached_version_ids = {document.version_id for document in attached_documents}
        selected_turn_stats = self._selected_turn_stats(previous_turns)
        return [
            self._routing_catalog_document_payload(
                summary=summary,
                attachment_state=(
                    "attached" if summary.version_id in attached_version_ids else "candidate"
                ),
                selected_turn_count=selected_turn_stats.get(summary.version_id, {}).get(
                    "selected_turn_count", 0
                ),
                last_selected_turn_index=selected_turn_stats.get(
                    summary.version_id, {}
                ).get("last_selected_turn_index"),
                selected_in_last_turn=selected_turn_stats.get(summary.version_id, {}).get(
                    "selected_in_last_turn", False
                ),
            )
            for summary in summaries
        ]

    def _routing_catalog_document_payload(
        self,
        *,
        summary: DocumentSummary,
        attachment_state: str,
        selected_turn_count: int,
        last_selected_turn_index: int | None,
        selected_in_last_turn: bool,
    ) -> dict[str, Any]:
        return {
            "file_id": summary.file_id,
            "version_id": summary.version_id,
            "attachment_state": attachment_state,
            "selected_turn_count": selected_turn_count,
            "last_selected_turn_index": last_selected_turn_index,
            "selected_in_last_turn": selected_in_last_turn,
            "summary_text": summary.summary_text,
            "business_domain": summary.business_domain,
            "key_topics": summary.key_topics,
            "sheet_summaries": [
                {
                    "sheet_name": sheet.sheet_name,
                    "summary": sheet.summary,
                }
                for sheet in summary.sheet_summaries
            ],
        }

    def _routing_memory_messages(self, turns: list[ChatTurn]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in turns:
            document_ids = [
                document.version_id for document in self._unique_documents(turn.selected_documents)
            ]
            messages.extend(
                [
                    {"role": "user", "content": turn.question},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {"document_for_this_turn_ids": document_ids},
                            ensure_ascii=False,
                        ),
                    },
                ]
            )
        return messages

    def _unique_documents(self, documents: list[SelectedDocument]) -> list[SelectedDocument]:
        unique_documents: list[SelectedDocument] = []
        seen_version_ids: set[str] = set()
        for document in documents:
            if document.version_id in seen_version_ids:
                continue
            seen_version_ids.add(document.version_id)
            unique_documents.append(document)
        return unique_documents

    def _turn_payload(self, turn: ChatTurn) -> dict[str, Any]:
        return {
            "question": turn.question,
            "assistant_answer": turn.answer_text,
            "citation_ids": turn.citation_ids,
            "selected_documents": [document.__dict__ for document in turn.selected_documents],
        }

    def _history_messages(self, turns: list[ChatTurn]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for turn in turns:
            metadata = {
                "citation_ids": turn.citation_ids,
                "selected_documents": [
                    document.__dict__ for document in turn.selected_documents
                ],
            }
            messages.extend(
                [
                    {"role": "user", "content": turn.question},
                    {
                        "role": "assistant",
                        "content": (
                            f"{turn.answer_text}\n\n"
                            "Previous answer metadata:\n"
                            f"{json.dumps(metadata, ensure_ascii=False)}"
                        ).strip(),
                    },
                ]
            )
        return messages

    def _request_messages(
        self,
        *,
        system_prompt: str | None,
        user_prompt: str | None,
        messages: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        if messages is not None:
            return messages
        if system_prompt is None or user_prompt is None:
            raise ExcelWorkspaceError("LLM request messages were not provided")
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _selected_turn_stats(
        self,
        previous_turns: list[ChatTurn],
    ) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        last_turn_index = len(previous_turns)
        for turn_index, turn in enumerate(previous_turns, start=1):
            for document in turn.selected_documents:
                entry = stats.setdefault(
                    document.version_id,
                    {
                        "selected_turn_count": 0,
                        "last_selected_turn_index": None,
                        "selected_in_last_turn": False,
                    },
                )
                entry["selected_turn_count"] += 1
                entry["last_selected_turn_index"] = turn_index
                entry["selected_in_last_turn"] = turn_index == last_turn_index
        return stats

    def _resolve_request(
        self,
        *,
        provider: str | None,
        model: str | None,
        stage: str,
    ) -> tuple[LlmProviderConfig, str]:
        provider_id = normalize_llm_provider(provider or self._default_providers[stage])
        if not is_supported_llm_provider(provider_id) or provider_id not in self._providers:
            raise ExcelWorkspaceError(f"unsupported {stage} provider '{provider_id}'")
        provider_config = self._providers[provider_id]
        default_model = self._default_model(provider_config, stage)
        resolved_model = (model or default_model).strip()
        if not is_supported_llm_model_for_provider(provider_id, resolved_model):
            raise InvalidLlmModelError(stage=stage, model=f"{provider_id}:{resolved_model}")
        return provider_config, resolved_model

    def _default_model(self, provider_config: LlmProviderConfig, stage: str) -> str:
        if stage == "summary":
            return provider_config.summary_model
        if stage == "router":
            return provider_config.router_model
        if stage == "answer":
            return provider_config.answer_model
        raise ExcelWorkspaceError(f"unknown LLM stage '{stage}'")

    def _provider_request_options(self, provider: str, model: str) -> dict[str, Any]:
        if provider == SILICONFLOW_PROVIDER and supports_enable_thinking_false(model):
            return {"enable_thinking": False}
        if provider == DEEPSEEK_PROVIDER:
            return {
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
            }
        return {}

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _object_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _optional_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


SiliconFlowLlmClient = MultiProviderLlmClient
