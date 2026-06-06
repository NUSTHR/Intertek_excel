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
            summary_text=(
                f"{profile.original_filename} contains {len(profile.sheets)} "
                f"sheet(s): {', '.join(sheet_names) or 'no sheets'}."
            ),
            business_domain="excel workbook",
            key_topics=key_topics,
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
                )
                for sheet in profile.sheets
            ],
            unsuitable_questions=[
                "Questions requiring information not present in this workbook.",
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
        cited_row_ids = [str(row["row_id"]) for row in rows[:3]]
        selected_count = len(documents)
        row_count = len(rows)
        return DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text=(
                        f"Draft answer for: {question} "
                        f"Selected {selected_count} document(s) and inspected {row_count} row(s)."
                    ),
                    evidence_row_ids=cited_row_ids[:1],
                )
            ],
            citations=[
                DraftCitation(row_id=row_id, quote=f"Evidence row {row_id}")
                for row_id in cited_row_ids
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
                *summary.suitable_questions,
                *[sheet.summary for sheet in summary.sheet_summaries],
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
