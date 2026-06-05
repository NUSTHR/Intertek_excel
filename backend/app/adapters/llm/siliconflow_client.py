import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2

from app.core.errors import ExcelWorkspaceError, InvalidLlmModelError, LlmRequestError
from app.core.ids import new_id
from app.core.llm_catalog import is_supported_llm_model, supports_enable_thinking_false
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
        "You are a conservative document router for an Excel question answering system.",
        "",
        "Your goal is to keep the active document set as small as possible while still "
        "sufficient for the current user turn.",
        "",
        "You are not trying to find every possibly related document.",
        "You are trying to determine whether the already attached documents are enough "
        "or whether a small number of additional documents must be added.",
        "",
        "Rules:",
        "1. Do not answer the user's question.",
        "2. Select only from the provided already attached documents and candidate new documents.",
        "3. Use version_id as the primary selection id.",
        "4. Prefer reusing already attached documents whenever they are still sufficient.",
        "5. Do not add new documents just because they are broadly related, adjacent, "
        "or potentially useful.",
        "6. Add new documents only when the current turn clearly introduces information "
        "needs that are not covered by the already attached documents.",
        "7. If already attached documents are sufficient, selected_documents should include "
        "only the documents that should remain active for this turn and should not add "
        "unrelated candidate documents.",
        "8. If no document is clearly relevant, return an empty selected_documents array.",
        "9. Prefer precision over recall.",
        "10. A document should be selected only if omitting it would likely miss necessary "
        "evidence for the current turn.",
        "11. The reason should be short and based on provided metadata or recent chat turns.",
        "12. Return strict JSON only. Do not return markdown, explanation, comments, "
        "or code fences.",
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


class SiliconFlowLlmClient:
    def __init__(
        self,
        config: SiliconFlowConfig,
        post: Callable[..., httpx2.Response] = httpx2.post,
    ) -> None:
        if not config.api_key.strip():
            raise ExcelWorkspaceError("LLM_API_KEY is required for SiliconFlow LLM calls")
        self._config = config
        self._post = post

    def generate_document_summary(
        self,
        profile: WorkbookProfile,
        *,
        model: str | None = None,
    ) -> DocumentSummary:
        payload = self._chat_json(
            stage="document_summary_model",
            model=self._resolve_model(model, self._config.summary_model, stage="summary"),
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
    ) -> list[SelectedDocument]:
        if not summaries:
            return []
        _ = max_documents
        user_questions_json = json.dumps(user_questions or [question], ensure_ascii=False)
        recent_turns_json = json.dumps(
            [self._turn_payload(turn) for turn in (previous_turns or [])[-3:]],
            ensure_ascii=False,
        )
        attached_documents_json = json.dumps(
            self._attached_routing_payload(
                summaries=summaries,
                attached_documents=attached_documents or [],
                previous_turns=previous_turns or [],
            ),
            ensure_ascii=False,
        )
        candidate_documents_json = json.dumps(
            self._candidate_routing_payload(
                summaries=summaries,
                attached_documents=attached_documents or [],
            ),
            ensure_ascii=False,
        )
        payload = self._chat_json(
            stage="route_model",
            model=self._resolve_model(model, self._config.router_model, stage="router"),
            system_prompt=DOCUMENT_ROUTER_SYSTEM_PROMPT,
            user_prompt=(
                "Route the current user turn.\n\n"
                "Current question:\n"
                f"{question}\n\n"
                "All session questions:\n"
                f"{user_questions_json}\n\n"
                "Recent chat turns:\n"
                f"{recent_turns_json}\n\n"
                "Already attached documents:\n"
                f"{attached_documents_json}\n\n"
                "Candidate new documents:\n"
                f"{candidate_documents_json}\n\n"
                "Return JSON in exactly this shape:\n\n"
                "{\n"
                '  "routing_decision": "reuse_attached | attach_incrementally | no_match",\n'
                '  "selected_documents": [\n'
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
        )
        selected = [
            SelectedDocument(
                file_id=str(item.get("file_id", "")),
                version_id=str(item.get("version_id", "")),
                reason=str(item.get("reason", "")),
                confidence=self._optional_float(item.get("confidence")),
            )
            for item in self._object_list(payload.get("selected_documents"))
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
    ) -> DraftChatAnswer:
        documents_json = json.dumps(
            [document.__dict__ for document in documents],
            ensure_ascii=False,
        )
        rows_json = json.dumps(rows, ensure_ascii=False)
        turns_json = json.dumps(
            [self._turn_payload(turn) for turn in previous_turns or []],
            ensure_ascii=False,
        )
        # #region debug-point C:answer-payload-shape
        self._debug_report(
            hypothesis_id="C",
            location="siliconflow_client.py:answer_with_rows",
            msg="[DEBUG] preparing answer_model payload",
            data={
                "question": question,
                "document_count": len(documents),
                "row_count": len(rows),
                "previous_turn_count": len(previous_turns or []),
                "selected_version_ids": [document.version_id for document in documents],
            },
        )
        # #endregion
        payload = self._chat_json(
            stage="answer_model",
            model=self._resolve_model(model, self._config.answer_model, stage="answer"),
            system_prompt=ANSWER_SYSTEM_PROMPT,
            user_prompt=(
                "Answer the question using the provided Excel rows.\n\n"
                f"Question:\n{question}\n\n"
                f"Previous chat turns:\n{turns_json}\n\n"
                f"Selected documents:\n{documents_json}\n\n"
                f"Rows:\n{rows_json}\n\n"
                "Each row object has file_id, version_id, sheet_id, sheet_name, row_id, cells.\n\n"
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
                "- quote should be a short snippet copied or summarized from the cited row.\n"
                "- If no provided row supports an answer, set insufficient_evidence to true "
                "and return empty citations."
            ),
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
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        content = self._chat_text(
            stage=stage,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._parse_json_object(content)

    def _chat_text(
        self,
        *,
        stage: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        url = f"{self._config.api_base_url.rstrip('/')}/chat/completions"
        request_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        request_payload.update(self._thinking_controls(model))
        # #region debug-point A:request-shape
        self._debug_report(
            hypothesis_id="A",
            location="siliconflow_client.py:_chat_text",
            msg="[DEBUG] sending llm request",
            data={
                "stage": stage,
                "model": model,
                "url": url,
                "request_keys": sorted(request_payload.keys()),
                "message_count": len(request_payload["messages"]),
                "system_prompt_chars": len(system_prompt),
                "user_prompt_chars": len(user_prompt),
                "thinking_controls": self._thinking_controls(model),
            },
        )
        # #endregion
        started_at = perf_counter()
        try:
            response = self._post(
                url,
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
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
            # #region debug-point B:http-error
            self._debug_report(
                hypothesis_id="B",
                location="siliconflow_client.py:_chat_text",
                msg="[DEBUG] llm request failed",
                data={
                    "stage": stage,
                    "model": model,
                    "duration_seconds": round(perf_counter() - started_at, 6),
                    "status_code": status_code,
                    "request_keys": sorted(request_payload.keys()),
                    "thinking_controls": self._thinking_controls(model),
                    "response_text_preview": response_text[:2000],
                },
            )
            # #endregion
            raise LlmRequestError(
                stage=stage,
                model=model,
                duration_seconds=perf_counter() - started_at,
                cause=exc,
            ) from exc
        # #region debug-point D:http-success
        self._debug_report(
            hypothesis_id="D",
            location="siliconflow_client.py:_chat_text",
            msg="[DEBUG] llm request succeeded",
            data={
                "stage": stage,
                "model": model,
                "status_code": response.status_code,
                "duration_seconds": round(perf_counter() - started_at, 6),
            },
        )
        # #endregion
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

    def _attached_routing_payload(
        self,
        *,
        summaries: list[DocumentSummary],
        attached_documents: list[AttachedDocument],
        previous_turns: list[ChatTurn],
    ) -> list[dict[str, Any]]:
        summary_by_version = {summary.version_id: summary for summary in summaries}
        selected_turn_stats = self._selected_turn_stats(previous_turns)
        return [
            self._attached_document_payload(
                document=document,
                summary=summary_by_version.get(document.version_id),
                selected_turn_count=selected_turn_stats.get(document.version_id, {}).get(
                    "selected_turn_count", 0
                ),
                last_selected_turn_index=selected_turn_stats.get(
                    document.version_id, {}
                ).get("last_selected_turn_index"),
                selected_in_last_turn=selected_turn_stats.get(document.version_id, {}).get(
                    "selected_in_last_turn", False
                ),
            )
            for document in attached_documents
            if document.version_id in summary_by_version
        ]

    def _candidate_routing_payload(
        self,
        *,
        summaries: list[DocumentSummary],
        attached_documents: list[AttachedDocument],
    ) -> list[dict[str, Any]]:
        attached_version_ids = {document.version_id for document in attached_documents}
        return [
            self._summary_payload(summary)
            for summary in summaries
            if summary.version_id not in attached_version_ids
        ]

    def _attached_document_payload(
        self,
        *,
        document: AttachedDocument,
        summary: DocumentSummary | None,
        selected_turn_count: int,
        last_selected_turn_index: int | None,
        selected_in_last_turn: bool,
    ) -> dict[str, Any]:
        payload = {
            "file_id": document.file_id,
            "version_id": document.version_id,
            "attached_at": document.attached_at,
            "row_count": document.row_count,
            "status": document.status,
            "selected_turn_count": selected_turn_count,
            "last_selected_turn_index": last_selected_turn_index,
            "selected_in_last_turn": selected_in_last_turn,
        }
        if summary is not None:
            payload.update(
                {
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
            )
        return payload

    def _turn_payload(self, turn: ChatTurn) -> dict[str, Any]:
        return {
            "question": turn.question,
            "assistant_answer": turn.answer_text,
            "citation_ids": turn.citation_ids,
            "selected_documents": [document.__dict__ for document in turn.selected_documents],
        }

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

    def _resolve_model(self, requested_model: str | None, default_model: str, *, stage: str) -> str:
        model = (requested_model or default_model).strip()
        if not is_supported_llm_model(model):
            raise InvalidLlmModelError(stage=stage, model=model)
        return model

    def _thinking_controls(self, model: str) -> dict[str, Any]:
        if supports_enable_thinking_false(model):
            return {"enable_thinking": False}
        return {}

    def _debug_report(
        self,
        *,
        hypothesis_id: str,
        location: str,
        msg: str,
        data: dict[str, Any],
    ) -> None:
        debug_server_url = "http://127.0.0.1:7777/event"
        debug_session_id = "deepseek-v32-400"
        env_paths = [
            os.path.join(".dbg", "deepseek-v32-400.env"),
            os.path.join("..", ".dbg", "deepseek-v32-400.env"),
        ]
        env_loaded = False
        for env_path in env_paths:
            try:
                with open(env_path, encoding="utf-8") as env_file:
                    for line in env_file:
                        if line.startswith("DEBUG_SERVER_URL="):
                            debug_server_url = line.split("=", 1)[1].strip()
                        elif line.startswith("DEBUG_SESSION_ID="):
                            debug_session_id = line.split("=", 1)[1].strip()
                env_loaded = True
                break
            except OSError:
                continue
        if not env_loaded:
            return
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    debug_server_url,
                    data=json.dumps(
                        {
                            "sessionId": debug_session_id,
                            "runId": "pre-fix",
                            "hypothesisId": hypothesis_id,
                            "location": location,
                            "msg": msg,
                            "data": data,
                        }
                    ).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                ),
                timeout=1,
            ).read()
        except Exception:
            return

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
