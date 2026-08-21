from app.application.pdf_knowledge.answer_grounding import (
    PdfAnswerEvidenceDocument,
    PdfAnswerEvidenceManifest,
    enforce_pdf_draft_grounding,
)
from app.domain.models import DraftAnswerBlock, DraftChatAnswer, DraftCitation


def test_grounding_gate_rejects_excluded_document_claim_with_valid_citation() -> None:
    manifest = PdfAnswerEvidenceManifest(
        documents=(
            PdfAnswerEvidenceDocument(
                file_id="pdf_1",
                file_name="included.pdf",
                evidence_ids=("pdf_1::chunk_1",),
            ),
        ),
        routed_candidate_count=2,
        selection_mode="vector_rerank",
        excluded_document_names=("excluded.pdf",),
    )
    result = enforce_pdf_draft_grounding(
        DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text="included.pdf and excluded.pdf both require traceability.",
                    evidence_ids=["pdf_1::chunk_1"],
                )
            ],
            citations=[
                DraftCitation(
                    evidence_id="pdf_1::chunk_1",
                    quote="model-authored quote must not make the block valid",
                )
            ],
            insufficient_evidence=False,
            follow_up_suggestions=[],
        ),
        manifest,
    )

    assert result.rejected_block_count == 1
    assert result.answer.answer_blocks == []
    assert result.answer.citations == []
    assert result.answer.insufficient_evidence is True


def test_grounding_gate_keeps_only_valid_evidence_on_accepted_blocks() -> None:
    manifest = PdfAnswerEvidenceManifest(
        documents=(
            PdfAnswerEvidenceDocument(
                file_id="pdf_1",
                file_name="included.pdf",
                evidence_ids=("pdf_1::chunk_1",),
            ),
        ),
        routed_candidate_count=1,
        selection_mode="router_only",
    )
    result = enforce_pdf_draft_grounding(
        DraftChatAnswer(
            answer_blocks=[
                DraftAnswerBlock(
                    text="The included evidence requires traceability.",
                    evidence_ids=["unknown", "pdf_1::chunk_1", "pdf_1::chunk_1"],
                ),
                DraftAnswerBlock(text="Uncited claim.", evidence_ids=[]),
            ],
            citations=[
                DraftCitation(evidence_id="unknown", quote="bad"),
                DraftCitation(evidence_id="pdf_1::chunk_1", quote="untrusted"),
            ],
            insufficient_evidence=False,
            follow_up_suggestions=[],
        ),
        manifest,
    )

    assert result.rejected_block_count == 1
    assert len(result.answer.answer_blocks) == 1
    assert result.answer.answer_blocks[0].evidence_ids == ["pdf_1::chunk_1"]
    assert result.answer.citations == [DraftCitation(evidence_id="pdf_1::chunk_1")]
    assert result.answer.insufficient_evidence is False
