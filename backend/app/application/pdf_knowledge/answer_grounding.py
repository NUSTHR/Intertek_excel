import re
from dataclasses import dataclass

from app.application.pdf_knowledge.chat_answer import evidence_id
from app.application.pdf_knowledge.models import PdfGroundingChunk
from app.domain.models import DraftAnswerBlock, DraftChatAnswer, DraftCitation, PdfFile


@dataclass(frozen=True)
class PdfAnswerEvidenceDocument:
    file_id: str
    file_name: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class PdfAnswerEvidenceManifest:
    documents: tuple[PdfAnswerEvidenceDocument, ...]
    routed_candidate_count: int
    selection_mode: str
    ranking_revision: str | None = None
    excluded_document_names: tuple[str, ...] = ()

    @property
    def final_document_count(self) -> int:
        return len(self.documents)

    @property
    def excluded_document_count(self) -> int:
        return max(0, self.routed_candidate_count - self.final_document_count)

    @property
    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(
            item_evidence_id
            for document in self.documents
            for item_evidence_id in document.evidence_ids
        )

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "selection_mode": self.selection_mode,
            "routed_candidate_count": self.routed_candidate_count,
            "final_document_count": self.final_document_count,
            "excluded_document_count": self.excluded_document_count,
            "ranking_revision": self.ranking_revision,
            "documents": [
                {
                    "document_ref": f"D{index}",
                    "file_id": document.file_id,
                    "file_name": document.file_name,
                    "evidence_ids": list(document.evidence_ids),
                }
                for index, document in enumerate(self.documents, start=1)
            ],
        }


@dataclass(frozen=True)
class PdfDraftGroundingResult:
    answer: DraftChatAnswer
    rejected_block_count: int
    rejected_follow_up_count: int


def build_pdf_answer_evidence_manifest(
    *,
    grounding_chunks: list[PdfGroundingChunk],
    routed_candidate_count: int,
    routed_files: list[PdfFile],
    selection_mode: str,
    ranking_revision: str | None,
) -> PdfAnswerEvidenceManifest:
    evidence_by_file_id: dict[str, list[str]] = {}
    file_name_by_id: dict[str, str] = {}
    ordered_file_ids: list[str] = []
    for item in grounding_chunks:
        file_id = item.file.file_id
        if file_id not in evidence_by_file_id:
            ordered_file_ids.append(file_id)
            evidence_by_file_id[file_id] = []
            file_name_by_id[file_id] = item.file.display_name
        evidence_by_file_id[file_id].append(evidence_id(item))
    final_file_ids = set(ordered_file_ids)
    return PdfAnswerEvidenceManifest(
        documents=tuple(
            PdfAnswerEvidenceDocument(
                file_id=file_id,
                file_name=file_name_by_id[file_id],
                evidence_ids=tuple(evidence_by_file_id[file_id]),
            )
            for file_id in ordered_file_ids
        ),
        routed_candidate_count=max(routed_candidate_count, len(ordered_file_ids)),
        selection_mode=selection_mode,
        ranking_revision=ranking_revision,
        excluded_document_names=tuple(
            file.display_name
            for file in routed_files
            if file.file_id not in final_file_ids
        ),
    )


def enforce_pdf_draft_grounding(
    draft: DraftChatAnswer,
    manifest: PdfAnswerEvidenceManifest,
) -> PdfDraftGroundingResult:
    allowed_evidence_ids = manifest.allowed_evidence_ids
    accepted_blocks: list[DraftAnswerBlock] = []
    rejected_blocks = 0
    for block in draft.answer_blocks:
        evidence_ids = list(
            dict.fromkeys(
                item_evidence_id
                for item_evidence_id in block.evidence_ids
                if item_evidence_id in allowed_evidence_ids
            )
        )
        if not block.text.strip() or not evidence_ids:
            rejected_blocks += 1
            continue
        if _contains_out_of_scope_claim(block.text, manifest):
            rejected_blocks += 1
            continue
        accepted_blocks.append(
            DraftAnswerBlock(
                text=block.text.strip(),
                evidence_ids=evidence_ids,
                reasoning=block.reasoning,
            )
        )

    cited_by_accepted_blocks = {
        item_evidence_id
        for block in accepted_blocks
        for item_evidence_id in block.evidence_ids
    }
    accepted_citations = [
        DraftCitation(evidence_id=item_evidence_id)
        for item_evidence_id in dict.fromkeys(
            citation.evidence_id
            for citation in draft.citations
            if citation.evidence_id in cited_by_accepted_blocks
        )
    ]
    accepted_follow_ups: list[str] = []
    rejected_follow_ups = 0
    for suggestion in draft.follow_up_suggestions:
        normalized = suggestion.strip()
        if not normalized or _contains_out_of_scope_claim(normalized, manifest):
            rejected_follow_ups += 1
            continue
        accepted_follow_ups.append(normalized)

    return PdfDraftGroundingResult(
        answer=DraftChatAnswer(
            answer_blocks=accepted_blocks,
            citations=accepted_citations,
            insufficient_evidence=draft.insufficient_evidence or not accepted_blocks,
            follow_up_suggestions=accepted_follow_ups,
        ),
        rejected_block_count=rejected_blocks,
        rejected_follow_up_count=rejected_follow_ups,
    )


def _contains_out_of_scope_claim(
    text: str,
    manifest: PdfAnswerEvidenceManifest,
) -> bool:
    normalized_text = " ".join(text.casefold().split())
    for file_name in manifest.excluded_document_names:
        normalized_name = " ".join(file_name.casefold().split())
        if normalized_name and normalized_name in normalized_text:
            return True
    if manifest.excluded_document_count <= 0:
        return False
    if any(
        phrase in normalized_text
        for phrase in (
            "all documents",
            "all pdfs",
            "every document",
            "全部文档",
            "所有文档",
            "全部pdf",
            "所有pdf",
            "每份文档",
        )
    ):
        return True
    routed_count = manifest.routed_candidate_count
    return bool(
        re.search(
            rf"(?:all|every)\s+(?:of\s+)?(?:the\s+)?{routed_count}\b",
            normalized_text,
        )
        or re.search(rf"(?:全部|所有)\s*{routed_count}\s*份", normalized_text)
        or re.search(rf"{routed_count}\s*份(?:文档|pdf)", normalized_text)
    )
