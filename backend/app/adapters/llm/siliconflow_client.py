import json
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2

from app.core.errors import ExcelWorkspaceError, LlmRequestError
from app.core.ids import new_id
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
        "You are a fast document router for an Excel question answering system.",
        "",
        "Your task is only to select relevant Excel document versions for the user question.",
        "",
        "Rules:",
        "1. Do not answer the user's question.",
        "2. Select only from the provided documents.",
        "3. Use version_id as the primary selection id.",
        "4. Select at most {max_documents} documents.",
        "5. If no document is relevant, return an empty selected_documents array.",
        "6. The reason should be short and based on filename, summary, key_topics, "
        "sheet names, or suitable questions.",
        "7. Return strict JSON only. Do not return markdown, explanation, comments, "
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

    def generate_document_summary(self, profile: WorkbookProfile) -> DocumentSummary:
        payload = self._chat_json(
            stage="document_summary_model",
            model=self._config.answer_model,
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
    ) -> list[SelectedDocument]:
        if not summaries:
            return []
        documents_json = json.dumps(
            [self._summary_payload(summary) for summary in summaries],
            ensure_ascii=False,
        )
        user_questions_json = json.dumps(user_questions or [question], ensure_ascii=False)
        attached_documents_json = json.dumps(
            [self._attached_document_payload(document) for document in attached_documents or []],
            ensure_ascii=False,
        )
        payload = self._chat_json(
            stage="route_model",
            model=self._config.router_model,
            system_prompt=DOCUMENT_ROUTER_SYSTEM_PROMPT.format(max_documents=max_documents),
            user_prompt=(
                "Select relevant Excel document versions for the question.\n\n"
                f"Question:\n{question}\n\n"
                "All user questions in this chat session:\n"
                f"{user_questions_json}\n\n"
                "Already attached document versions in this chat session:\n"
                f"{attached_documents_json}\n\n"
                f"Documents:\n{documents_json}\n\n"
                "Return JSON in exactly this shape:\n\n"
                "{\n"
                '  "selected_documents": [\n'
                "    {\n"
                '      "file_id": "string",\n'
                '      "version_id": "string",\n'
                '      "reason": "string",\n'
                '      "confidence": 0.0\n'
                "    }\n"
                "  ],\n"
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
        return [
            document
            for document in selected[:max(1, max_documents)]
            if allowed.get(document.version_id) == document.file_id
        ]

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
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
        payload = self._chat_json(
            stage="answer_model",
            model=self._config.answer_model,
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
            raise LlmRequestError(
                stage=stage,
                model=model,
                duration_seconds=perf_counter() - started_at,
                cause=exc,
            ) from exc
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

    def _attached_document_payload(self, document: AttachedDocument) -> dict[str, Any]:
        return {
            "file_id": document.file_id,
            "version_id": document.version_id,
            "attached_at": document.attached_at,
            "row_count": document.row_count,
            "status": document.status,
        }

    def _turn_payload(self, turn: ChatTurn) -> dict[str, Any]:
        return {
            "question": turn.question,
            "assistant_answer": turn.answer_text,
            "citation_ids": turn.citation_ids,
            "selected_documents": [document.__dict__ for document in turn.selected_documents],
        }

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
