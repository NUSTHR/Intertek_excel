import pytest

from app.application.pdf_knowledge.document_selection import (
    MAX_FINAL_PDF_DOCUMENTS,
    PdfFinalDocumentSelection,
    PdfRankedDocument,
    PdfRoutingCandidateSet,
    PdfSelectionMode,
)
from app.core.errors import PdfSelectionIntegrityError
from app.domain.models import SelectedDocument


def document(index: int) -> SelectedDocument:
    return SelectedDocument(
        file_id=f"file_{index}",
        version_id=f"file_{index}",
        reason=f"router reason {index}",
        confidence=0.5,
    )


def candidate_set(count: int) -> PdfRoutingCandidateSet:
    return PdfRoutingCandidateSet(tuple(document(index) for index in range(count)))


def rankings(count: int) -> tuple[PdfRankedDocument, ...]:
    return tuple(
        PdfRankedDocument(
            file_id=f"file_{index}",
            rank=index + 1,
            score=1.0 - index / max(1, count),
            evidence_chunk_ids=(f"chunk_{index}",),
        )
        for index in range(count)
    )


@pytest.mark.parametrize("count", range(MAX_FINAL_PDF_DOCUMENTS + 1))
def test_router_only_selection_preserves_zero_to_four_candidates(count: int) -> None:
    candidates = candidate_set(count)

    selection = PdfFinalDocumentSelection.router_only(candidates)

    assert selection.mode is PdfSelectionMode.ROUTER_ONLY
    assert selection.documents == candidates.documents
    assert selection.rankings == ()
    assert selection.ranking_revision is None


def test_more_than_four_candidates_cannot_use_router_only_selection() -> None:
    with pytest.raises(
        PdfSelectionIntegrityError,
        match="require vector reranking",
    ):
        PdfFinalDocumentSelection.router_only(candidate_set(5))


def test_vector_reranking_selects_the_first_four_ranked_candidates() -> None:
    candidates = candidate_set(6)
    ranked = rankings(6)

    selection = PdfFinalDocumentSelection.vector_rerank(
        candidates=candidates,
        rankings=ranked,
        ranking_revision="Qwen3-Reranker-8B@revision-1",
    )

    assert selection.mode is PdfSelectionMode.VECTOR_RERANK
    assert [item.file_id for item in selection.documents] == [
        "file_0",
        "file_1",
        "file_2",
        "file_3",
    ]
    assert selection.rankings == ranked


def test_vector_reranking_must_evaluate_every_candidate() -> None:
    with pytest.raises(
        PdfSelectionIntegrityError,
        match="evaluate every routing candidate",
    ):
        PdfFinalDocumentSelection.vector_rerank(
            candidates=candidate_set(6),
            rankings=rankings(5),
            ranking_revision="revision-1",
        )


def test_vector_reranking_cannot_include_a_document_outside_router_candidates() -> None:
    ranked = list(rankings(5))
    ranked[-1] = PdfRankedDocument(
        file_id="outside_file",
        rank=5,
        score=0.1,
        evidence_chunk_ids=("outside_chunk",),
    )

    with pytest.raises(
        PdfSelectionIntegrityError,
        match="exactly match the routing candidates",
    ):
        PdfFinalDocumentSelection.vector_rerank(
            candidates=candidate_set(5),
            rankings=tuple(ranked),
            ranking_revision="revision-1",
        )


def test_vector_reranking_rejects_non_contiguous_ranks() -> None:
    ranked = list(rankings(5))
    ranked[1] = PdfRankedDocument(
        file_id="file_1",
        rank=3,
        score=0.8,
        evidence_chunk_ids=("chunk_1",),
    )

    with pytest.raises(PdfSelectionIntegrityError, match="contiguous ranks"):
        PdfFinalDocumentSelection.vector_rerank(
            candidates=candidate_set(5),
            rankings=tuple(ranked),
            ranking_revision="revision-1",
        )


def test_routing_candidates_reject_duplicate_file_ids() -> None:
    with pytest.raises(PdfSelectionIntegrityError, match="must be unique"):
        PdfRoutingCandidateSet((document(1), document(1)))


@pytest.mark.parametrize("score", [float("inf"), float("-inf"), float("nan")])
def test_ranked_document_score_must_be_finite(score: float) -> None:
    with pytest.raises(PdfSelectionIntegrityError, match="must be finite"):
        PdfRankedDocument(
            file_id="file_1",
            rank=1,
            score=score,
            evidence_chunk_ids=("chunk_1",),
        )
