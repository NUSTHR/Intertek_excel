import math
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import PdfSelectionIntegrityError
from app.domain.models import SelectedDocument

MAX_FINAL_PDF_DOCUMENTS = 4


class PdfSelectionMode(StrEnum):
    ROUTER_ONLY = "router_only"
    VECTOR_RERANK = "vector_rerank"


@dataclass(frozen=True)
class PdfRoutingCandidateSet:
    documents: tuple[SelectedDocument, ...]

    def __post_init__(self) -> None:
        _validate_unique_documents(self.documents, stage="routing candidates")

    @property
    def file_ids(self) -> tuple[str, ...]:
        return tuple(document.file_id for document in self.documents)


@dataclass(frozen=True)
class PdfRankedDocument:
    file_id: str
    rank: int
    score: float
    evidence_chunk_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.file_id.strip():
            raise PdfSelectionIntegrityError("ranked document file_id must not be blank")
        if self.rank < 1:
            raise PdfSelectionIntegrityError("ranked document rank must be positive")
        if not math.isfinite(self.score):
            raise PdfSelectionIntegrityError("ranked document score must be finite")
        if not self.evidence_chunk_ids:
            raise PdfSelectionIntegrityError(
                "ranked document must contain retrieval evidence"
            )
        normalized_chunk_ids = tuple(
            chunk_id.strip() for chunk_id in self.evidence_chunk_ids
        )
        if any(not chunk_id for chunk_id in normalized_chunk_ids):
            raise PdfSelectionIntegrityError("evidence chunk IDs must not be blank")
        if len(set(normalized_chunk_ids)) != len(normalized_chunk_ids):
            raise PdfSelectionIntegrityError("evidence chunk IDs must be unique")


@dataclass(frozen=True)
class PdfFinalDocumentSelection:
    candidates: PdfRoutingCandidateSet
    documents: tuple[SelectedDocument, ...]
    mode: PdfSelectionMode
    rankings: tuple[PdfRankedDocument, ...] = ()
    ranking_revision: str | None = None

    def __post_init__(self) -> None:
        _validate_unique_documents(self.documents, stage="final selection")
        candidate_count = len(self.candidates.documents)
        if candidate_count <= MAX_FINAL_PDF_DOCUMENTS:
            self._validate_router_only_selection()
            return
        self._validate_vector_rerank_selection()

    @classmethod
    def router_only(
        cls,
        candidates: PdfRoutingCandidateSet,
    ) -> "PdfFinalDocumentSelection":
        return cls(
            candidates=candidates,
            documents=candidates.documents,
            mode=PdfSelectionMode.ROUTER_ONLY,
        )

    @classmethod
    def vector_rerank(
        cls,
        *,
        candidates: PdfRoutingCandidateSet,
        rankings: tuple[PdfRankedDocument, ...],
        ranking_revision: str,
    ) -> "PdfFinalDocumentSelection":
        candidate_by_file_id = {
            document.file_id: document for document in candidates.documents
        }
        final_documents = tuple(
            candidate_by_file_id[ranking.file_id]
            for ranking in rankings[:MAX_FINAL_PDF_DOCUMENTS]
            if ranking.file_id in candidate_by_file_id
        )
        return cls(
            candidates=candidates,
            documents=final_documents,
            mode=PdfSelectionMode.VECTOR_RERANK,
            rankings=rankings,
            ranking_revision=ranking_revision,
        )

    def _validate_router_only_selection(self) -> None:
        if self.mode is not PdfSelectionMode.ROUTER_ONLY:
            raise PdfSelectionIntegrityError(
                "four or fewer routing candidates must use router-only selection"
            )
        if self.documents != self.candidates.documents:
            raise PdfSelectionIntegrityError(
                "router-only selection must preserve every candidate and its order"
            )
        if self.rankings:
            raise PdfSelectionIntegrityError(
                "router-only selection must not contain ranking results"
            )
        if self.ranking_revision is not None:
            raise PdfSelectionIntegrityError(
                "router-only selection must not contain a ranking revision"
            )

    def _validate_vector_rerank_selection(self) -> None:
        if self.mode is not PdfSelectionMode.VECTOR_RERANK:
            raise PdfSelectionIntegrityError(
                "more than four routing candidates require vector reranking"
            )
        if len(self.documents) != MAX_FINAL_PDF_DOCUMENTS:
            raise PdfSelectionIntegrityError(
                "vector reranking must select exactly four documents"
            )
        if not self.ranking_revision or not self.ranking_revision.strip():
            raise PdfSelectionIntegrityError(
                "vector reranking requires a non-blank ranking revision"
            )
        candidate_file_ids = self.candidates.file_ids
        ranked_file_ids = tuple(ranking.file_id for ranking in self.rankings)
        if len(self.rankings) != len(candidate_file_ids):
            raise PdfSelectionIntegrityError(
                "vector reranking must evaluate every routing candidate"
            )
        if len(set(ranked_file_ids)) != len(ranked_file_ids):
            raise PdfSelectionIntegrityError("ranked document IDs must be unique")
        if set(ranked_file_ids) != set(candidate_file_ids):
            raise PdfSelectionIntegrityError(
                "ranked documents must exactly match the routing candidates"
            )
        expected_ranks = tuple(range(1, len(self.rankings) + 1))
        actual_ranks = tuple(ranking.rank for ranking in self.rankings)
        if actual_ranks != expected_ranks:
            raise PdfSelectionIntegrityError(
                "ranked documents must be ordered with contiguous ranks"
            )
        expected_final_file_ids = ranked_file_ids[:MAX_FINAL_PDF_DOCUMENTS]
        actual_final_file_ids = tuple(document.file_id for document in self.documents)
        if actual_final_file_ids != expected_final_file_ids:
            raise PdfSelectionIntegrityError(
                "final documents must be the first four ranked candidates"
            )


def _validate_unique_documents(
    documents: tuple[SelectedDocument, ...],
    *,
    stage: str,
) -> None:
    file_ids: list[str] = []
    for document in documents:
        file_id = document.file_id.strip()
        if not file_id:
            raise PdfSelectionIntegrityError(f"{stage} file_id must not be blank")
        file_ids.append(file_id)
    if len(set(file_ids)) != len(file_ids):
        raise PdfSelectionIntegrityError(f"{stage} file IDs must be unique")
