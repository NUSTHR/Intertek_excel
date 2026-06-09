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


class FakeLlmClient:
    def generate_document_summary(
        self,
        profile: WorkbookProfile,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> DocumentSummary:
        _ = model, provider
        sheet_names = [sheet.sheet_name for sheet in profile.sheets]
        key_topics = self._unique_values(
            [
                profile.original_filename,
                *sheet_names,
                *[
                    value
                    for sheet in profile.sheets
                    for value in sheet.candidate_header[:8]
                    if value
                ],
            ]
        )[:12]
        return DocumentSummary(
            summary_id=new_id("summary"),
            file_id=profile.file_id,
            version_id=profile.version_id,
            document_title=profile.original_filename,
            document_type="excel_workbook",
            summary_text=(
                f"{profile.original_filename} contains {len(profile.sheets)} "
                f"sheet(s): {', '.join(sheet_names) or 'no sheets'}."
            ),
            business_domain="excel workbook",
            coverage_scope={
                "business_processes": ["rows", "sheet contents"],
            },
            key_topics=key_topics,
            positive_routing_terms=key_topics,
            negative_routing_terms=[],
            exact_identifiers=key_topics,
            suitable_questions=[
                "Ask about rows, sheet contents, dates, remarks, and listed values.",
            ],
            sheet_summaries=[
                SheetSummary(
                    sheet_id=sheet.sheet_id,
                    sheet_name=sheet.sheet_name,
                    summary=(
                        f"{sheet.sheet_name} has {sheet.row_count} rows and "
                        f"{sheet.column_count} columns."
                    ),
                    important_columns=sheet.candidate_header[:8],
                    likely_question_types=["row lookup", "sheet content summary"],
                    header_terms=sheet.candidate_header[:8],
                    sampled_identifiers=self._unique_values(
                        [
                            cell
                            for row in (sheet.profile_rows or sheet.sample_rows)[:20]
                            for cell in row
                            if cell
                        ]
                    )[:20],
                )
                for sheet in profile.sheets
            ],
            unsuitable_questions=[
                "Questions requiring information not present in this workbook.",
            ],
            routing_notes="fake routing card generated from workbook profile",
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
        _ = user_questions, attached_documents, previous_turns, model, provider
        scored = sorted(
            summaries,
            key=lambda summary: self._score(question, summary),
            reverse=True,
        )
        return [
            SelectedDocument(
                file_id=summary.file_id,
                version_id=summary.version_id,
                reason="selected by summary keyword overlap",
                confidence=0.5,
            )
            for summary in scored[:max(1, max_documents)]
            if self._score(question, summary) > 0 or len(summaries) == 1
        ]

    def answer_with_rows(
        self,
        question: str,
        documents: list[SelectedDocument],
        rows: list[dict],
        previous_turns: list[ChatTurn] | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> DraftChatAnswer:
        _ = previous_turns, model, provider
        cited_evidence_ids = [str(row["evidence_id"]) for row in rows[:3]]
        selected_count = len(documents)
        row_count = len(rows)
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=(
                        f"Draft answer for: {question} "
                        f"Selected {selected_count} document(s) and inspected {row_count} row(s)."
                    ),
                    evidence_ids=cited_evidence_ids[:1],
                )
            ],
            citations=[
                DraftCitation(
                    evidence_id=evidence_id,
                    quote=f"Evidence row {evidence_id}",
                )
                for evidence_id in cited_evidence_ids
            ],
            insufficient_evidence=False,
            follow_up_suggestions=[],
        )

    def _score(self, question: str, summary: DocumentSummary) -> int:
        haystack = " ".join(
            [
                summary.summary_text,
                summary.business_domain,
                *summary.key_topics,
                *summary.positive_routing_terms,
                *summary.exact_identifiers,
                *summary.suitable_questions,
                *[sheet.summary for sheet in summary.sheet_summaries],
                *[
                    value
                    for sheet in summary.sheet_summaries
                    for value in [*sheet.header_terms, *sheet.sampled_identifiers]
                ],
            ]
        ).lower()
        return sum(1 for token in self._tokens(question) if token in haystack)

    def _tokens(self, text: str) -> list[str]:
        return [token for token in text.lower().replace("_", " ").split() if token]

    def _unique_values(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
