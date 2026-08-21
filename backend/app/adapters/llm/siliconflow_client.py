import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2

from app.core.errors import (
    ExcelWorkspaceError,
    InvalidLlmModelError,
    LlmRequestError,
    LlmResponseFormatError,
    PdfRoutingError,
)
from app.core.ids import new_id
from app.core.llm_catalog import (
    SILICONFLOW_PROVIDER,
    is_supported_llm_model_for_provider,
    is_supported_llm_provider,
    llm_provider_label,
    normalize_llm_provider,
    supports_deep_thinking,
    supports_json_response_format,
    thinking_request_style,
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
from app.ports.llm_client import CancellationChecker

logger = logging.getLogger(__name__)

_PDF_ROUTING_RETRY_RESERVE_CHARACTERS = 9_000
_PDF_ROUTING_DOCUMENT_TITLE_CHARACTERS = 500
_PDF_ROUTING_SUMMARY_CHARACTERS = 4_000
_PDF_ROUTING_NOTES_CHARACTERS = 2_000
_PDF_ROUTING_LIST_ITEM_CHARACTERS = 256
_PDF_ROUTING_LIST_LIMITS = {
    "key_topics": 32,
    "positive_routing_terms": 48,
    "negative_routing_terms": 32,
    "exact_identifiers": 64,
    "suitable_questions": 24,
    "unsuitable_questions": 24,
}

DOCUMENT_SUMMARY_SYSTEM_PROMPT = "\n".join(
    [
        "You are an Excel document profiling assistant for a third-party testing, "
        "inspection, and certification company.",
        "",
        "Your task is to generate a compact routing index card for one Excel workbook "
        "version in an enterprise knowledge base.",
        "",
        "You will receive only deterministic workbook profile data extracted by the backend:",
        "filename, sheet metadata, candidate headers, row counts, column counts, and "
        "all normalized workbook rows.",
        "",
        "Business context:",
        "- Workbooks may describe products, models, materials, customers, suppliers, "
        "test plans, test reports, certificates, standards, directives, regulations, "
        "country requirements, lab capabilities, quotations, project trackers, or "
        "compliance matrices.",
        "- Common routing identifiers include product names, model numbers, standard "
        "families such as IEC/EN/UL/CSA/GB/ISO/ASTM, regulation names, directives such "
        "as LVD/EMC/RED/MD/RoHS/REACH, certificate/report numbers, countries, regions, "
        "brands, factories, and business process terms.",
        "",
        "Rules:",
        "1. Use only the provided profile facts.",
        "2. Do not invent rows, columns, business meanings, dates, standards, products, "
        "or conclusions that are not supported by the profile.",
        "3. The result is used for document routing, not as a factual answer source.",
        "4. Keep all identifiers exactly as provided, especially file_id, version_id, "
        "sheet_id, and sheet_name.",
        "5. Prefer short, searchable phrases. Avoid long prose.",
        "6. exact_identifiers must contain only identifiers visible in the workbook, "
        "for example standards, directives, model names, report numbers, regions, or "
        "other exact lookup terms.",
        "7. positive_routing_terms should contain terms that strongly suggest this "
        "workbook should be selected.",
        "8. negative_routing_terms should contain terms that help reject adjacent but "
        "wrong questions.",
        "9. suitable_questions should be natural user questions this workbook is likely "
        "able to help answer.",
        "10. unsuitable_questions should describe questions this workbook likely cannot "
        "answer.",
        "11. Return strict JSON only. Do not return markdown, explanation, comments, "
        "or code fences.",
    ]
)

DOCUMENT_ROUTER_SYSTEM_PROMPT = "\n".join(
    [
        "You are a fast document router for an enterprise Excel question answering "
        "system used by a third-party testing, inspection, and certification company.",
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
        "4. Work fast: classify documents from catalog metadata only. Do not perform "
        "deep answer reasoning.",
        "5. First extract the current turn's routing requirements: product/model, "
        "standard or regulation family, region/country, business process, value type, "
        "and any exact identifiers.",
        "6. Use routing memory only to resolve conversational context, such as follow-up "
        "questions, pronouns, abbreviations, refinements, repeated product context, "
        "or references to previous turns.",
        "7. If the current turn still needs evidence from a document selected earlier, "
        "include that document again in document_for_this_turn. Do not omit it merely "
        "because it was selected before.",
        "8. If the current turn introduces a new product, model, region, regulation type, "
        "standard family, document family, or business topic, choose candidate documents "
        "only when their routing card indicates likely evidence.",
        "9. Do not keep old attached documents for the current turn just because they were "
        "used earlier. Include them only when they are useful for the current turn.",
        "10. Do not add documents that are merely adjacent, generic, or weakly related.",
        "11. A strong match requires exact or near-exact overlap with filename, document "
        "title, exact_identifiers, positive_routing_terms, coverage_scope, sheet names, "
        "or important columns.",
        "12. Generic words such as test, report, standard, file, product, value, date, "
        "price, supplier, or certificate are not enough by themselves.",
        "13. Use negative_routing_terms and unsuitable_questions to reject documents.",
        "14. If no catalog document is likely to contain evidence for the current turn, "
        "return an empty document_for_this_turn array.",
        "15. Default to empty: if you are not confident that a document contains direct "
        "evidence for the current turn, do not select it.",
        "16. Dangerous-to-miss exception: if the user asks about a specific product, "
        "model, regulation, standard, region, certificate/report number, or numerical "
        "value and a document routing card explicitly covers that exact identifier, "
        "include it even if the question is terse.",
        "17. Keep reasons short and diagnostic: cite the matched identifiers or say why "
        "the conservative default was applied.",
        "18. Return strict JSON only. Do not return markdown, explanation, comments, "
        "or code fences.",
    ]
)

PDF_DOCUMENT_ROUTER_SYSTEM_PROMPT = """
You are a document router for an enterprise PDF knowledge base.

The candidate catalog already contains only visible, READY PDFs inside the exact
file, folder, or All PDF sources scope selected by the user. Choose only the PDF
documents needed to answer the current turn.

Rules:
1. Do not answer the user's question.
2. Select only IDs present in the candidate catalog.
3. Use version_id as the selection ID.
4. Use routing memory only to resolve follow-ups, pronouns, and refinements.
5. Do not reuse a previously selected document unless it is relevant to this turn.
6. Questions that explicitly request all, every, each, a summary of the current
   folder/scope, or a comparison of the selected scope are range-wide intents.
   For such intents, select the distinct candidate documents needed to cover the
   scope, up to the supplied maximum.
7. Candidates with the same non-empty duplicate_content_group are copies. Unless
   the question explicitly asks about copies or versions, select only the member
   whose duplicate_content_canonical value is true. If copies or versions are
   explicitly requested, select every relevant copy. Also avoid obvious duplicate
   copies whose title and routing summary are materially identical.
8. For ordinary fact questions, select only strong semantic or identifier matches.
9. If no candidate is likely to contain evidence, return an empty array.
10. The catalog may be one transport batch from a larger scope. Classify every
    candidate in this batch independently and return every relevant candidate in
    this batch. Do not apply a top-k ranking inside the batch.
11. Return strict JSON only. Do not return Markdown, comments, rejected-document
    lists, routing analysis, or explanatory text outside the JSON object.
""".strip()

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
8. Split the answer into separate answer_blocks by claim, paragraph, bullet, or table row
   whenever different evidence supports different parts of the answer.
9. Each answer_block must include only the evidence_ids that support that block's text.
10. Do not collect all citations at the end of the answer or in one final answer block.
11. Return strict JSON only. Do not return markdown, comments, explanations, or code fences.
""".strip()

PDF_ANSWER_SYSTEM_PROMPT = """
You are an enterprise PDF knowledge-base answer assistant.

You answer user questions using only the provided PDF chunks.

Rules:
1. Use only the provided chunks as evidence.
2. Do not use outside knowledge.
3. Previous user and assistant messages are conversation memory only. Use them
   to resolve follow-ups, pronouns, omissions, comparisons, and refinements.
4. Never treat a previous assistant answer or its citation metadata as current
   evidence. Every factual claim in the current answer must be supported by the
   PDF chunks supplied in the current user message.
5. Every factual claim based on PDF content must cite one or more evidence refs.
6. Citations must reference evidence_id values from the provided chunks only.
7. Do not invent file_id, chunk_id, page labels, titles, or document content.
8. If the provided chunks are insufficient, say so clearly.
9. Keep the answer concise and business-readable.
10. Split the answer into separate answer_blocks by claim, paragraph, bullet, or table row
   whenever different evidence supports different parts of the answer.
11. Each answer_block must include only the evidence_ids that support that block's text.
12. Do not collect all citations at the end of the answer or in one final answer block.
13. Return strict JSON only. Do not return markdown, comments, explanations, or code fences.
14. The authoritative document manifest defines the complete evidence scope for
    this turn. A document mentioned in the question or conversation history is
    not evidence unless it appears in that manifest.
15. Never claim that you inspected, compared, or verified more documents than
    final_document_count. Never mention a document that is absent from the manifest.
""".strip()

PDF_ANSWER_GROUNDING_VERIFIER_SYSTEM_PROMPT = """
You are a strict evidence-grounding verifier for an enterprise PDF assistant.

Evaluate the draft against only the current chunks and authoritative document
manifest. Reject the draft if any factual claim lacks supporting evidence, if it
mentions a document outside the manifest, or if it claims broader document
coverage than final_document_count. Conversation history and the user's wording
are never evidence. Return strict JSON only with this shape:
{"supported": true, "violations": []}

Do not return reasoning, markdown, revised answer text, or any additional keys.
""".strip()

PDF_ANSWER_GROUNDING_REPAIR_SYSTEM_PROMPT = """
You repair an enterprise PDF answer using only the supplied current PDF chunks.

Remove every unsupported statement and every reference to a document outside the
authoritative manifest. Never claim broader coverage than final_document_count.
Every answer block must contain supporting evidence_id values from the supplied
chunks. If a grounded answer cannot be produced, return no answer blocks and set
insufficient_evidence to true. Return strict JSON only.
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
    pdf_routing_max_request_characters: int = 120_000
    pdf_routing_max_batch_documents: int = 20


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
                label=llm_provider_label(SILICONFLOW_PROVIDER),
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
                "Generate a routing index card for this Excel workbook profile.\n\n"
                "Return JSON in exactly this shape:\n\n"
                "{\n"
                '  "document_title": "string",\n'
                '  "document_type": "string",\n'
                '  "summary_text": "string",\n'
                '  "business_domain": "string",\n'
                '  "coverage_scope": {\n'
                '    "products": ["string"],\n'
                '    "models": ["string"],\n'
                '    "regions": ["string"],\n'
                '    "regulation_types": ["string"],\n'
                '    "standards": ["string"],\n'
                '    "business_processes": ["string"]\n'
                "  },\n"
                '  "key_topics": ["string"],\n'
                '  "positive_routing_terms": ["string"],\n'
                '  "negative_routing_terms": ["string"],\n'
                '  "exact_identifiers": ["string"],\n'
                '  "suitable_questions": ["string"],\n'
                '  "unsuitable_questions": ["string"],\n'
                '  "sheet_summaries": [\n'
                "    {\n"
                '      "sheet_id": "string",\n'
                '      "sheet_name": "string",\n'
                '      "summary": "string",\n'
                '      "important_columns": ["string"],\n'
                '      "likely_question_types": ["string"],\n'
                '      "header_terms": ["string"],\n'
                '      "sampled_identifiers": ["string"]\n'
                "    }\n"
                "  ],\n"
                '  "routing_notes": "string"\n'
                "}\n\n"
                "Guidance:\n"
                "- document_type should be a short category such as standard_matrix, "
                "test_report, certificate_tracker, product_requirement_table, "
                "quote_cost_table, project_tracker, supplier_list, or unknown.\n"
                "- Keep summary_text under 80 words.\n"
                "- Keep lists concise and searchable. Prefer exact strings from cells.\n\n"
                "Workbook profile:\n"
                f"{json.dumps(self._profile_payload(profile), ensure_ascii=False)}"
            ),
        )
        allowed_sheet_ids = {sheet.sheet_id for sheet in profile.sheets}
        return DocumentSummary(
            summary_id=new_id("summary"),
            file_id=profile.file_id,
            version_id=profile.version_id,
            document_title=str(payload.get("document_title", "")).strip()
            or profile.original_filename,
            document_type=str(payload.get("document_type", "unknown")).strip()
            or "unknown",
            summary_text=str(payload.get("summary_text", "")).strip()
            or f"{profile.original_filename} contains {len(profile.sheets)} sheet(s).",
            business_domain=str(payload.get("business_domain", "excel workbook")).strip()
            or "excel workbook",
            coverage_scope=self._scope_map(payload.get("coverage_scope")),
            key_topics=self._string_list(payload.get("key_topics")),
            positive_routing_terms=self._string_list(payload.get("positive_routing_terms")),
            negative_routing_terms=self._string_list(payload.get("negative_routing_terms")),
            exact_identifiers=self._string_list(payload.get("exact_identifiers")),
            suitable_questions=self._string_list(payload.get("suitable_questions")),
            unsuitable_questions=self._string_list(payload.get("unsuitable_questions")),
            sheet_summaries=[
                SheetSummary(
                    sheet_id=str(sheet.get("sheet_id", "")),
                    sheet_name=str(sheet.get("sheet_name", "")),
                    summary=str(sheet.get("summary", "")),
                    important_columns=self._string_list(sheet.get("important_columns")),
                    likely_question_types=self._string_list(sheet.get("likely_question_types")),
                    header_terms=self._string_list(sheet.get("header_terms")),
                    sampled_identifiers=self._string_list(sheet.get("sampled_identifiers")),
                )
                for sheet in self._object_list(payload.get("sheet_summaries"))
                if str(sheet.get("sheet_id", "")) in allowed_sheet_ids
            ],
            routing_notes=str(payload.get("routing_notes", "")).strip(),
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
        cancellation_checker: CancellationChecker | None = None,
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
            cancellation_checker=cancellation_checker,
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
                        "Use this fast process:\n"
                        "1. Extract routing_requirements from the current question and "
                        "routing memory.\n"
                        "2. Classify each candidate as strong_match, weak_match, or "
                        "no_match.\n"
                        "3. Return only strong matches. Use weak matches only when no "
                        "strong match exists and the reason is explicit.\n\n"
                        "Current question:\n"
                        f"{question}\n\n"
                        "Return JSON in exactly this shape:\n\n"
                        "{\n"
                        '  "routing_requirements": {\n'
                        '    "products": ["string"],\n'
                        '    "models": ["string"],\n'
                        '    "regions": ["string"],\n'
                        '    "regulation_types": ["string"],\n'
                        '    "standards": ["string"],\n'
                        '    "business_processes": ["string"],\n'
                        '    "exact_identifiers": ["string"]\n'
                        "  },\n"
                        '  "routing_decision": '
                        '"reuse_attached | attach_incrementally | no_match",\n'
                        '  "document_for_this_turn": [\n'
                        "    {\n"
                        '      "file_id": "string",\n'
                        '      "version_id": "string",\n'
                        '      "match_level": "strong_match | weak_match",\n'
                        '      "matched_terms": ["string"],\n'
                        '      "missing_terms": ["string"],\n'
                        '      "reason": "string",\n'
                        '      "confidence": 0.0\n'
                        "    }\n"
                        "  ],\n"
                        '  "rejected_documents": [\n'
                        "    {\n"
                        '      "version_id": "string",\n'
                        '      "reason": "string"\n'
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
        raw_selected_items = self._object_list(
            payload.get("document_for_this_turn", payload.get("selected_documents"))
        )
        selected = self._filter_router_selection(
            selected=selected,
            raw_items=raw_selected_items,
            max_documents=max_documents,
        )
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

    def route_pdf_documents(
        self,
        question: str,
        summaries: list[DocumentSummary],
        max_documents: int,
        user_questions: list[str] | None = None,
        attached_documents: list[AttachedDocument] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        cancellation_checker: CancellationChecker | None = None,
    ) -> list[SelectedDocument]:
        if not summaries or max_documents <= 0:
            return []
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="router",
        )
        _ = user_questions
        routing_memory = self._routing_memory_messages(previous_turns or [])
        document_batches = self._pdf_routing_document_batches(
            catalog=self._pdf_routing_document_catalog(
                summaries=summaries,
                attached_documents=attached_documents or [],
                previous_turns=previous_turns or [],
            ),
            question=question,
            routing_memory=routing_memory,
        )
        logger.info(
            "routing PDF document catalog candidate_count=%s batch_count=%s",
            len(summaries),
            len(document_batches),
        )
        selected_by_version_id: dict[str, SelectedDocument] = {}
        for batch_index, document_batch in enumerate(document_batches, start=1):
            messages = self._pdf_routing_messages(
                document_catalog_json=self._compact_json(document_batch),
                question=question,
                routing_memory=routing_memory,
                batch_document_count=len(document_batch),
            )
            try:
                payload = self._chat_json(
                    stage="pdf_route_model",
                    provider_config=provider_config,
                    model=resolved_model,
                    cancellation_checker=cancellation_checker,
                    messages=messages,
                    allow_embedded_json=True,
                    invalid_json_retry_prompt=(
                        "Your previous response was not a complete JSON object. Return "
                        'only the compact object {"document_for_this_turn": [...]} now. '
                        "Do not include rejected documents, analysis, Markdown, or code "
                        "fences."
                    ),
                    max_request_characters=(
                        self._config.pdf_routing_max_request_characters
                    ),
                )
            except LlmResponseFormatError as exc:
                raise PdfRoutingError(
                    "PDF document routing returned an invalid response. Please retry."
                ) from exc

            selected = self._validated_pdf_router_selection(
                payload=payload,
                document_batch=document_batch,
            )
            for document in selected:
                selected_by_version_id[document.version_id] = document
            logger.info(
                "completed PDF routing batch batch_index=%s batch_count=%s "
                "candidate_count=%s selected_count=%s",
                batch_index,
                len(document_batches),
                len(document_batch),
                len(selected),
            )

        ordered_selected = [
            selected_by_version_id[summary.version_id]
            for summary in summaries
            if summary.version_id in selected_by_version_id
        ]
        result = ordered_selected[:max_documents]
        logger.info(
            "completed PDF document routing candidate_count=%s selected_count=%s "
            "returned_count=%s",
            len(summaries),
            len(ordered_selected),
            len(result),
        )
        return result

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
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
        payload, reasoning_content = self._chat_json_with_reasoning(
            stage="answer_model",
            provider_config=provider_config,
            model=resolved_model,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
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
                        "row_id, evidence_id, cells.\n\n"
                        "Return JSON in exactly this shape:\n\n"
                        "{\n"
                        '  "answer_blocks": [\n'
                        "    {\n"
                        '      "text": "string",\n'
                        '      "evidence_ids": ["string"]\n'
                        "    }\n"
                        "  ],\n"
                        '  "citations": [\n'
                        "    {\n"
                        '      "evidence_id": "string",\n'
                        '      "version_id": "string",\n'
                        '      "sheet_id": "string",\n'
                        '      "row_id": "string",\n'
                        '      "quote": "string"\n'
                        "    }\n"
                        "  ],\n"
                        '  "insufficient_evidence": false,\n'
                        '  "follow_up_suggestions": ["string"]\n'
                        "}\n\n"
                        "Important:\n"
                        "- evidence_ids must contain only evidence_id values from Rows.\n"
                        "- Split answer_blocks so each independent claim, paragraph, bullet, "
                        "or table row carries its own evidence_ids.\n"
                        "- Do not put all evidence_ids into the last block. Do not create a "
                        "separate citations-only block.\n"
                        "- Prefer using evidence_id everywhere citations are needed.\n"
                        "- citation version_id, sheet_id, and row_id must match one row "
                        "object from Rows exactly when they are included.\n"
                        "- If evidence_id is provided in a citation object, it must match "
                        "one row object from Rows exactly.\n"
                        "- quote should be a short snippet copied or summarized from the "
                        "cited row.\n"
                        "- If no provided row supports an answer, set insufficient_evidence "
                        "to true and return empty citations."
                    ),
                },
            ],
        )
        answer_blocks = [
            DraftAnswerBlock(
                text=str(block.get("text", "")).strip(),
                evidence_ids=self._string_list(
                    block.get("evidence_ids", block.get("evidence_row_ids"))
                ),
                reasoning=reasoning_content if index == 0 else "",
            )
            for index, block in enumerate(self._object_list(payload.get("answer_blocks")))
            if str(block.get("text", "")).strip()
        ]
        return DraftChatAnswer(
            answer_blocks=answer_blocks,
            citations=[
                DraftCitation(
                    evidence_id=str(citation.get("evidence_id", "")).strip(),
                    quote=str(citation.get("quote", "")).strip(),
                    version_id=str(citation.get("version_id", "")).strip(),
                    sheet_id=str(citation.get("sheet_id", "")).strip(),
                    row_id=str(citation.get("row_id", "")).strip(),
                )
                for citation in self._object_list(payload.get("citations"))
                if any(
                    [
                        str(citation.get("evidence_id", "")).strip(),
                        str(citation.get("row_id", "")).strip(),
                    ]
                )
            ],
            insufficient_evidence=bool(payload.get("insufficient_evidence", False)),
            follow_up_suggestions=self._string_list(payload.get("follow_up_suggestions")),
        )

    def answer_with_pdf_chunks(
        self,
        question: str,
        chunks: list[dict],
        document_manifest: dict[str, object] | None = None,
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> DraftChatAnswer:
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="answer",
        )
        chunks_json = json.dumps(chunks, ensure_ascii=False)
        manifest_json = json.dumps(document_manifest or {}, ensure_ascii=False)
        logger.debug(
            "preparing PDF answer model payload chunk_count=%s previous_turn_count=%s",
            len(chunks),
            len(previous_turns or []),
        )
        payload, reasoning_content = self._chat_json_with_reasoning(
            stage="pdf_answer_model",
            provider_config=provider_config,
            model=resolved_model,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
            messages=[
                {"role": "system", "content": PDF_ANSWER_SYSTEM_PROMPT},
                *self._history_messages(previous_turns or []),
                {
                    "role": "user",
                    "content": (
                        "Answer the question using the provided PDF chunks.\n\n"
                        f"Question:\n{question}\n\n"
                        f"Authoritative document manifest:\n{manifest_json}\n\n"
                        f"Chunks:\n{chunks_json}\n\n"
                        "Each chunk object has evidence_id, file_id, file_name, "
                        "chunk_id, chunk_index, token_count, page_label, title, "
                        "text, and excerpt.\n\n"
                        "Return JSON in exactly this shape:\n\n"
                        "{\n"
                        '  "answer_blocks": [\n'
                        "    {\n"
                        '      "text": "string",\n'
                        '      "evidence_ids": ["string"]\n'
                        "    }\n"
                        "  ],\n"
                        '  "citations": [\n'
                        "    {\n"
                        '      "evidence_id": "string",\n'
                        '      "quote": "string"\n'
                        "    }\n"
                        "  ],\n"
                        '  "insufficient_evidence": false,\n'
                        '  "follow_up_suggestions": ["string"]\n'
                        "}\n\n"
                        "Important:\n"
                        "- evidence_ids must contain only evidence_id values from Chunks.\n"
                        "- Treat the authoritative document manifest as a hard scope boundary.\n"
                        "- If the question asks about more documents than final_document_count, "
                        "state that the answer covers only the manifest documents; do not claim "
                        "to have checked excluded documents.\n"
                        "- Prefer using evidence_id everywhere citations are needed.\n"
                        "- quote should be a short snippet copied or summarized from the "
                        "cited chunk.\n"
                        "- When evidence spans multiple selected PDFs, synthesize across "
                        "them and preserve file-specific citations.\n"
                        "- If no provided chunk supports an answer, set insufficient_evidence "
                        "to true and return empty citations."
                    ),
                },
            ],
        )
        return self._pdf_draft_answer_from_payload(payload, reasoning_content)

    def verify_and_repair_pdf_answer(
        self,
        *,
        question: str,
        chunks: list[dict],
        document_manifest: dict[str, object],
        draft_answer: DraftChatAnswer,
        model: str | None = None,
        provider: str | None = None,
        cancellation_checker: CancellationChecker | None = None,
    ) -> DraftChatAnswer | None:
        provider_config, resolved_model = self._resolve_request(
            provider=provider,
            model=model,
            stage="answer",
        )
        chunks_json = json.dumps(chunks, ensure_ascii=False)
        manifest_json = json.dumps(document_manifest, ensure_ascii=False)
        draft_json = json.dumps(
            {
                "answer_blocks": [
                    {
                        "text": block.text,
                        "evidence_ids": block.evidence_ids,
                    }
                    for block in draft_answer.answer_blocks
                ],
                "citations": [
                    {"evidence_id": citation.evidence_id}
                    for citation in draft_answer.citations
                ],
                "insufficient_evidence": draft_answer.insufficient_evidence,
                "follow_up_suggestions": draft_answer.follow_up_suggestions,
            },
            ensure_ascii=False,
        )
        supported, violations = self._verify_pdf_answer_payload(
            provider_config=provider_config,
            model=resolved_model,
            question=question,
            chunks_json=chunks_json,
            manifest_json=manifest_json,
            draft_json=draft_json,
            cancellation_checker=cancellation_checker,
        )
        if supported:
            return draft_answer

        repair_payload, repair_reasoning = self._chat_json_with_reasoning(
            stage="pdf_answer_grounding_repair",
            provider_config=provider_config,
            model=resolved_model,
            enable_deep_thinking=False,
            cancellation_checker=cancellation_checker,
            messages=[
                {"role": "system", "content": PDF_ANSWER_GROUNDING_REPAIR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Authoritative document manifest:\n{manifest_json}\n\n"
                        f"Chunks:\n{chunks_json}\n\n"
                        f"Rejected draft:\n{draft_json}\n\n"
                        f"Violation codes:\n{json.dumps(violations, ensure_ascii=False)}\n\n"
                        "Return JSON with answer_blocks, citations, "
                        "insufficient_evidence, and follow_up_suggestions using the "
                        "same schema as the rejected draft."
                    ),
                },
            ],
        )
        repaired = self._pdf_draft_answer_from_payload(
            repair_payload,
            repair_reasoning,
        )
        repaired_json = json.dumps(
            {
                "answer_blocks": [
                    {"text": block.text, "evidence_ids": block.evidence_ids}
                    for block in repaired.answer_blocks
                ],
                "citations": [
                    {"evidence_id": citation.evidence_id}
                    for citation in repaired.citations
                ],
                "insufficient_evidence": repaired.insufficient_evidence,
                "follow_up_suggestions": repaired.follow_up_suggestions,
            },
            ensure_ascii=False,
        )
        repaired_supported, _ = self._verify_pdf_answer_payload(
            provider_config=provider_config,
            model=resolved_model,
            question=question,
            chunks_json=chunks_json,
            manifest_json=manifest_json,
            draft_json=repaired_json,
            cancellation_checker=cancellation_checker,
        )
        return repaired if repaired_supported else None

    def _verify_pdf_answer_payload(
        self,
        *,
        provider_config: LlmProviderConfig,
        model: str,
        question: str,
        chunks_json: str,
        manifest_json: str,
        draft_json: str,
        cancellation_checker: CancellationChecker | None,
    ) -> tuple[bool, list[str]]:
        payload, _reasoning = self._chat_json_with_reasoning(
            stage="pdf_answer_grounding_verifier",
            provider_config=provider_config,
            model=model,
            enable_deep_thinking=False,
            cancellation_checker=cancellation_checker,
            messages=[
                {
                    "role": "system",
                    "content": PDF_ANSWER_GROUNDING_VERIFIER_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Authoritative document manifest:\n{manifest_json}\n\n"
                        f"Chunks:\n{chunks_json}\n\n"
                        f"Draft answer:\n{draft_json}"
                    ),
                },
            ],
        )
        supported = payload.get("supported") is True
        violations = self._string_list(payload.get("violations"))
        if not supported and not violations:
            violations = ["UNSUPPORTED_DRAFT"]
        return supported, violations

    def _pdf_draft_answer_from_payload(
        self,
        payload: dict[str, object],
        reasoning_content: str,
    ) -> DraftChatAnswer:
        answer_blocks = [
            DraftAnswerBlock(
                text=str(block.get("text", "")).strip(),
                evidence_ids=self._string_list(
                    block.get("evidence_ids", block.get("evidence_chunk_ids"))
                ),
                reasoning=reasoning_content if index == 0 else "",
            )
            for index, block in enumerate(self._object_list(payload.get("answer_blocks")))
            if str(block.get("text", "")).strip()
        ]
        return DraftChatAnswer(
            answer_blocks=answer_blocks,
            citations=[
                DraftCitation(
                    evidence_id=str(citation.get("evidence_id", "")).strip(),
                    quote=str(citation.get("quote", "")).strip(),
                )
                for citation in self._object_list(payload.get("citations"))
                if str(citation.get("evidence_id", "")).strip()
            ],
            insufficient_evidence=bool(payload.get("insufficient_evidence", False)),
            follow_up_suggestions=self._string_list(payload.get("follow_up_suggestions")),
        )

    def _chat_json_with_reasoning(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> tuple[dict[str, Any], str]:
        content, reasoning_content = self._chat_message_parts(
            stage=stage,
            provider_config=provider_config,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
        )
        return self._parse_json_object(content), reasoning_content

    def _chat_json(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
        allow_embedded_json: bool = False,
        invalid_json_retry_prompt: str | None = None,
        max_request_characters: int | None = None,
    ) -> dict[str, Any]:
        self._validate_message_character_budget(
            messages=messages,
            max_request_characters=max_request_characters,
        )
        content, _reasoning_content = self._chat_message_parts(
            stage=stage,
            provider_config=provider_config,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
        )
        try:
            return self._parse_json_object(
                content,
                allow_embedded=allow_embedded_json,
            )
        except LlmResponseFormatError:
            if not invalid_json_retry_prompt or messages is None:
                raise
        retry_messages = [
            *messages,
            {"role": "assistant", "content": content[:8000]},
            {"role": "user", "content": invalid_json_retry_prompt},
        ]
        self._validate_message_character_budget(
            messages=retry_messages,
            max_request_characters=max_request_characters,
        )
        retry_content, _retry_reasoning = self._chat_message_parts(
            stage=stage,
            provider_config=provider_config,
            model=model,
            messages=retry_messages,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
        )
        return self._parse_json_object(
            retry_content,
            allow_embedded=allow_embedded_json,
        )

    def _validate_message_character_budget(
        self,
        *,
        messages: list[dict[str, str]] | None,
        max_request_characters: int | None,
    ) -> None:
        if messages is None or max_request_characters is None:
            return
        if len(self._compact_json(messages)) > max_request_characters:
            raise LlmResponseFormatError(
                "LLM request exceeds the configured character budget"
            )

    def _chat_text(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> str:
        content, _reasoning_content = self._chat_message_parts(
            stage=stage,
            provider_config=provider_config,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages=messages,
            enable_deep_thinking=enable_deep_thinking,
            cancellation_checker=cancellation_checker,
        )
        return content

    def _chat_message_parts(
        self,
        *,
        stage: str,
        provider_config: LlmProviderConfig,
        model: str,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        messages: list[dict[str, str]] | None = None,
        enable_deep_thinking: bool = False,
        cancellation_checker: CancellationChecker | None = None,
    ) -> tuple[str, str]:
        if not provider_config.api_key.strip():
            raise ExcelWorkspaceError(f"{provider_config.label} API key is required for LLM calls")
        if cancellation_checker is not None:
            cancellation_checker()

        url = f"{provider_config.api_base_url.rstrip('/')}/chat/completions"
        request_payload = {
            "model": model,
            "messages": self._request_messages(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                messages=messages,
            ),
            "temperature": self._temperature_for_stage(stage),
        }
        max_tokens = self._max_tokens_for_stage(stage)
        if max_tokens is not None:
            request_payload["max_tokens"] = max_tokens
        provider_options = self._provider_request_options(
            provider_config.provider,
            model,
            enable_deep_thinking=enable_deep_thinking,
        )
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
            if cancellation_checker is not None:
                cancellation_checker()
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
                provider=provider_config.provider,
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
        if cancellation_checker is not None:
            cancellation_checker()
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") == "length":
                raise LlmResponseFormatError(
                    "LLM response reached the output token limit"
                )
            logger.debug(
                "llm response metadata stage=%s finish_reason=%s content_length=%s",
                stage,
                choice.get("finish_reason"),
                len(str(message.get("content") or "")),
            )
            return (
                str(message["content"]),
                str(message.get("reasoning_content") or "").strip(),
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmResponseFormatError(
                "LLM response did not include message content"
            ) from exc

    def _parse_json_object(
        self,
        content: str,
        *,
        allow_embedded: bool = False,
    ) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError as original_exc:
            if not allow_embedded:
                raise LlmResponseFormatError() from original_exc
            object_start = text.find("{")
            if object_start < 0:
                raise LlmResponseFormatError() from original_exc
            try:
                value, _end = json.JSONDecoder().raw_decode(text[object_start:])
            except json.JSONDecodeError as exc:
                raise LlmResponseFormatError() from exc
        if not isinstance(value, dict):
            raise LlmResponseFormatError("LLM response JSON must be an object")
        return value

    def _profile_payload(self, profile: WorkbookProfile) -> dict[str, Any]:
        return {
            "file_id": profile.file_id,
            "version_id": profile.version_id,
            "original_filename": profile.original_filename,
            "file_hash": profile.file_hash,
            "sheets": [
                {
                    "sheet_id": sheet.sheet_id,
                    "sheet_code": sheet.sheet_code,
                    "sheet_name": sheet.sheet_name,
                    "row_count": sheet.row_count,
                    "column_count": sheet.column_count,
                    "candidate_header": sheet.candidate_header,
                    "sample_rows": sheet.sample_rows[: self._config.summary_max_profile_rows],
                    "all_rows": sheet.profile_rows or sheet.sample_rows,
                }
                for sheet in profile.sheets
            ],
        }

    def _summary_payload(self, summary: DocumentSummary) -> dict[str, Any]:
        return {
            "file_id": summary.file_id,
            "version_id": summary.version_id,
            "document_title": summary.document_title,
            "document_type": summary.document_type,
            "summary_text": summary.summary_text,
            "business_domain": summary.business_domain,
            "coverage_scope": summary.coverage_scope,
            "key_topics": summary.key_topics,
            "positive_routing_terms": summary.positive_routing_terms,
            "negative_routing_terms": summary.negative_routing_terms,
            "exact_identifiers": summary.exact_identifiers,
            "suitable_questions": summary.suitable_questions,
            "unsuitable_questions": summary.unsuitable_questions,
            "routing_notes": summary.routing_notes,
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

    def _pdf_routing_document_catalog(
        self,
        *,
        summaries: list[DocumentSummary],
        attached_documents: list[AttachedDocument],
        previous_turns: list[ChatTurn],
    ) -> list[dict[str, Any]]:
        attached_version_ids = {document.version_id for document in attached_documents}
        selected_turn_stats = self._selected_turn_stats(previous_turns)
        catalog: list[dict[str, Any]] = []
        seen_duplicate_groups: set[str] = set()
        for summary in summaries:
            duplicate_groups = summary.coverage_scope.get(
                "duplicate_content_group", []
            )
            duplicate_group = (
                str(duplicate_groups[0] or "").strip()
                if isinstance(duplicate_groups, list) and duplicate_groups
                else ""
            )
            duplicate_content_canonical = (
                not duplicate_group or duplicate_group not in seen_duplicate_groups
            )
            if duplicate_group:
                seen_duplicate_groups.add(duplicate_group)
            catalog.append(
                self._compact_pdf_routing_card(
                    {
                        "file_id": summary.file_id,
                        "version_id": summary.version_id,
                        "document_title": summary.document_title,
                        "duplicate_content_group": duplicate_group or None,
                        "duplicate_content_canonical": duplicate_content_canonical,
                        "attachment_state": (
                            "attached"
                            if summary.version_id in attached_version_ids
                            else "candidate"
                        ),
                        "selected_turn_count": selected_turn_stats.get(
                            summary.version_id, {}
                        ).get("selected_turn_count", 0),
                        "selected_in_last_turn": selected_turn_stats.get(
                            summary.version_id, {}
                        ).get("selected_in_last_turn", False),
                        "summary_text": summary.summary_text,
                        "key_topics": summary.key_topics,
                        "positive_routing_terms": summary.positive_routing_terms,
                        "negative_routing_terms": summary.negative_routing_terms,
                        "exact_identifiers": summary.exact_identifiers,
                        "suitable_questions": summary.suitable_questions,
                        "unsuitable_questions": summary.unsuitable_questions,
                        "routing_notes": summary.routing_notes,
                    }
                )
            )
        return catalog

    def _compact_pdf_routing_card(self, card: dict[str, Any]) -> dict[str, Any]:
        compact_card = {
            "file_id": str(card.get("file_id", "")).strip(),
            "version_id": str(card.get("version_id", "")).strip(),
            "document_title": self._bounded_text(
                card.get("document_title"),
                _PDF_ROUTING_DOCUMENT_TITLE_CHARACTERS,
            ),
            "duplicate_content_group": self._bounded_text(
                card.get("duplicate_content_group"),
                _PDF_ROUTING_LIST_ITEM_CHARACTERS,
            )
            or None,
            "duplicate_content_canonical": bool(
                card.get("duplicate_content_canonical", True)
            ),
            "attachment_state": str(card.get("attachment_state", "candidate")),
            "selected_turn_count": card.get("selected_turn_count", 0),
            "selected_in_last_turn": bool(card.get("selected_in_last_turn", False)),
            "summary_text": self._bounded_text(
                card.get("summary_text"),
                _PDF_ROUTING_SUMMARY_CHARACTERS,
            ),
            "routing_notes": self._bounded_text(
                card.get("routing_notes"),
                _PDF_ROUTING_NOTES_CHARACTERS,
            ),
        }
        for field_name, item_limit in _PDF_ROUTING_LIST_LIMITS.items():
            compact_card[field_name] = self._bounded_string_list(
                card.get(field_name),
                item_limit=item_limit,
            )
        return compact_card

    def _pdf_routing_document_batches(
        self,
        *,
        catalog: list[dict[str, Any]],
        question: str,
        routing_memory: list[dict[str, str]],
    ) -> list[list[dict[str, Any]]]:
        max_request_characters = self._config.pdf_routing_max_request_characters
        max_batch_documents = self._config.pdf_routing_max_batch_documents
        if max_request_characters <= _PDF_ROUTING_RETRY_RESERVE_CHARACTERS:
            raise PdfRoutingError(
                "PDF routing request budget is too small for a safe model request."
            )
        if max_batch_documents < 1:
            raise PdfRoutingError("PDF routing batch size must be positive.")
        if max_batch_documents > 20:
            raise PdfRoutingError(
                "PDF routing batch size exceeds the safe router output limit."
            )

        seen_version_ids: set[str] = set()
        for card in catalog:
            file_id = str(card.get("file_id", "")).strip()
            version_id = str(card.get("version_id", "")).strip()
            if not file_id or not version_id:
                raise PdfRoutingError("PDF routing catalog contains an empty ID.")
            if version_id in seen_version_ids:
                raise PdfRoutingError(
                    "PDF routing catalog contains a duplicate version ID."
                )
            seen_version_ids.add(version_id)

        batches: list[list[dict[str, Any]]] = []
        current_batch: list[dict[str, Any]] = []
        for card in catalog:
            candidate_batch = [*current_batch, card]
            if (
                len(candidate_batch) <= max_batch_documents
                and self._pdf_routing_batch_fits(
                    document_batch=candidate_batch,
                    question=question,
                    routing_memory=routing_memory,
                )
            ):
                current_batch = candidate_batch
                continue
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            if not self._pdf_routing_batch_fits(
                document_batch=[card],
                question=question,
                routing_memory=routing_memory,
            ):
                raise PdfRoutingError(
                    "A PDF routing card cannot fit within the configured request budget."
                )
            current_batch = [card]
        if current_batch:
            batches.append(current_batch)
        return batches

    def _pdf_routing_batch_fits(
        self,
        *,
        document_batch: list[dict[str, Any]],
        question: str,
        routing_memory: list[dict[str, str]],
    ) -> bool:
        messages = self._pdf_routing_messages(
            document_catalog_json=self._compact_json(document_batch),
            question=question,
            routing_memory=routing_memory,
            batch_document_count=len(document_batch),
        )
        request_characters = len(self._compact_json(messages))
        return (
            request_characters + _PDF_ROUTING_RETRY_RESERVE_CHARACTERS
            <= self._config.pdf_routing_max_request_characters
        )

    def _pdf_routing_messages(
        self,
        *,
        document_catalog_json: str,
        question: str,
        routing_memory: list[dict[str, str]],
        batch_document_count: int,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": PDF_DOCUMENT_ROUTER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "PDF candidate catalog for the current transport batch:\n\n"
                    f"{document_catalog_json}"
                ),
            },
            *routing_memory,
            {
                "role": "user",
                "content": (
                    "Route the current PDF question. Classify every candidate in this "
                    "batch; do not rank or truncate relevant candidates.\n\n"
                    f"Candidates in this batch: {batch_document_count}\n"
                    f"Maximum documents for this turn: {batch_document_count}\n\n"
                    f"Current question:\n{question}\n\n"
                    "Return JSON in exactly this compact shape:\n"
                    "{\n"
                    '  "document_for_this_turn": [\n'
                    "    {\n"
                    '      "file_id": "candidate file_id",\n'
                    '      "version_id": "candidate version_id",\n'
                    '      "reason": "short matched topic or range-wide reason",\n'
                    '      "confidence": 0.0\n'
                    "    }\n"
                    "  ]\n"
                    "}"
                ),
            },
        ]

    def _validated_pdf_router_selection(
        self,
        *,
        payload: dict[str, Any],
        document_batch: list[dict[str, Any]],
    ) -> list[SelectedDocument]:
        if "document_for_this_turn" in payload:
            raw_value = payload["document_for_this_turn"]
        elif "selected_documents" in payload:
            raw_value = payload["selected_documents"]
        else:
            raise PdfRoutingError(
                "PDF document routing response omitted the selection list."
            )
        if not isinstance(raw_value, list) or any(
            not isinstance(item, dict) for item in raw_value
        ):
            raise PdfRoutingError(
                "PDF document routing response has an invalid selection list."
            )
        raw_selected_items: list[dict[str, Any]] = raw_value
        allowed_pairs = {
            (str(card["file_id"]), str(card["version_id"]))
            for card in document_batch
        }
        seen_version_ids: set[str] = set()
        selected: list[SelectedDocument] = []
        for item in raw_selected_items:
            file_id = str(item.get("file_id", "")).strip()
            version_id = str(item.get("version_id", "")).strip()
            if (file_id, version_id) not in allowed_pairs:
                raise PdfRoutingError(
                    "PDF document routing returned an ID outside the current batch."
                )
            if version_id in seen_version_ids:
                raise PdfRoutingError(
                    "PDF document routing returned a duplicate version ID."
                )
            seen_version_ids.add(version_id)
            selected.append(
                SelectedDocument(
                    file_id=file_id,
                    version_id=version_id,
                    reason=str(item.get("reason", "")),
                    confidence=self._optional_float(item.get("confidence")),
                )
            )
        return self._filter_router_selection(
            selected=selected,
            raw_items=raw_selected_items,
            max_documents=len(document_batch),
        )

    def _bounded_text(self, value: Any, max_characters: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_characters:
            return text
        return text[: max_characters - 1].rstrip() + "…"

    def _bounded_string_list(self, value: Any, *, item_limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value[:item_limit]:
            text = self._bounded_text(item, _PDF_ROUTING_LIST_ITEM_CHARACTERS)
            if text:
                result.append(text)
        return result

    def _compact_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

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
            "document_title": summary.document_title,
            "document_type": summary.document_type,
            "attachment_state": attachment_state,
            "selected_turn_count": selected_turn_count,
            "last_selected_turn_index": last_selected_turn_index,
            "selected_in_last_turn": selected_in_last_turn,
            "summary_text": summary.summary_text,
            "business_domain": summary.business_domain,
            "coverage_scope": summary.coverage_scope,
            "key_topics": summary.key_topics,
            "positive_routing_terms": summary.positive_routing_terms,
            "negative_routing_terms": summary.negative_routing_terms,
            "exact_identifiers": summary.exact_identifiers,
            "suitable_questions": summary.suitable_questions,
            "unsuitable_questions": summary.unsuitable_questions,
            "routing_notes": summary.routing_notes,
            "sheet_summaries": [
                {
                    "sheet_id": sheet.sheet_id,
                    "sheet_name": sheet.sheet_name,
                    "summary": sheet.summary,
                    "important_columns": sheet.important_columns,
                    "likely_question_types": sheet.likely_question_types,
                    "header_terms": sheet.header_terms,
                    "sampled_identifiers": sheet.sampled_identifiers,
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

    def _provider_request_options(
        self,
        provider: str,
        model: str,
        *,
        enable_deep_thinking: bool = False,
    ) -> dict[str, Any]:
        return {
            **self._json_response_format_options(provider),
            **self._thinking_request_options(
                provider,
                model,
                enable_deep_thinking=enable_deep_thinking,
            ),
        }

    def _json_response_format_options(self, provider: str) -> dict[str, Any]:
        if supports_json_response_format(provider):
            return {"response_format": {"type": "json_object"}}
        return {}

    def _thinking_request_options(
        self,
        provider: str,
        model: str,
        *,
        enable_deep_thinking: bool,
    ) -> dict[str, Any]:
        request_style = thinking_request_style(provider, model)
        if request_style == "siliconflow_enable_thinking":
            return {
                "enable_thinking": bool(
                    enable_deep_thinking and supports_deep_thinking(provider, model)
                )
            }
        if request_style != "deepseek_thinking":
            return {}
        if enable_deep_thinking:
            return {
                "thinking": {"type": "enabled"},
                "reasoning_effort": "high",
            }
        return {"thinking": {"type": "disabled"}}

    def _temperature_for_stage(self, stage: str) -> float:
        if stage in {"route_model", "pdf_route_model"}:
            return 0.0
        return 0.2

    def _max_tokens_for_stage(self, stage: str) -> int | None:
        if stage == "document_summary_model":
            return 4096
        if stage == "route_model":
            return 1200
        if stage == "pdf_route_model":
            return 1600
        if stage in {"answer_model", "pdf_answer_model"}:
            return 4096
        return None

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _scope_map(self, value: Any) -> dict[str, list[str]]:
        if not isinstance(value, dict):
            return {}
        scope: dict[str, list[str]] = {}
        for key, items in value.items():
            values = self._string_list(items)
            if values:
                scope[str(key)] = values
        return scope

    def _object_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def _optional_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _filter_router_selection(
        self,
        *,
        selected: list[SelectedDocument],
        raw_items: list[dict[str, Any]],
        max_documents: int,
    ) -> list[SelectedDocument]:
        filtered: list[SelectedDocument] = []
        for document, raw_item in zip(selected, raw_items, strict=False):
            match_level = str(raw_item.get("match_level", "")).strip()
            matched_terms = self._string_list(raw_item.get("matched_terms"))
            if not match_level and not matched_terms:
                filtered.append(document)
                continue
            confidence = document.confidence if document.confidence is not None else 0.0
            if match_level == "weak_match" and confidence < 0.65:
                continue
            if match_level not in {"strong_match", "weak_match"}:
                continue
            if not matched_terms and confidence < 0.85:
                continue
            filtered.append(document)
        return filtered[: max(0, max_documents)]


SiliconFlowLlmClient = MultiProviderLlmClient
