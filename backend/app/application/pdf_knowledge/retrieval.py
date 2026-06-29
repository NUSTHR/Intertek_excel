import re
from dataclasses import dataclass

from app.application.pdf_knowledge.models import (
    PdfChunkSearchMatch,
    PdfChunkSearchResult,
)
from app.core.errors import AssetNotFoundError, UploadValidationError
from app.domain.models import (
    PdfDocumentChunk,
    PdfFile,
    PdfFileKind,
    PdfFileVisibility,
    PdfProcessingStatus,
    UserRole,
)
from app.ports.repository import PdfKnowledgeRepository

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass(frozen=True)
class PdfRetrievalPolicy:
    default_limit: int = 12
    max_limit: int = 50
    excerpt_radius: int = 90
    title_weight: float = 2.5
    exact_query_weight: float = 4.0

    def normalize_query(self, query: str) -> str:
        return " ".join(query.split())

    def normalize_limit(self, limit: int | None) -> int:
        requested_limit = self.default_limit if limit is None else limit
        return max(1, min(self.max_limit, requested_limit))

    def query_terms(self, query: str) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in TOKEN_PATTERN.findall(query.casefold()):
            if token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms


class PdfRetrievalService:
    def __init__(
        self,
        *,
        repository: PdfKnowledgeRepository,
        policy: PdfRetrievalPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy or PdfRetrievalPolicy()

    def search_chunks(
        self,
        *,
        query: str,
        file_ids: list[str] | None,
        limit: int | None,
        user_role: UserRole,
    ) -> PdfChunkSearchResult:
        normalized_query = self._policy.normalize_query(query)
        if not normalized_query:
            raise UploadValidationError("PDF search query is required")
        safe_limit = self._policy.normalize_limit(limit)
        terms = self._policy.query_terms(normalized_query)
        if not terms:
            raise UploadValidationError("PDF search query is required")
        files = self._candidate_files(file_ids=file_ids, user_role=user_role)
        matches = self._rank_matches(
            files=files,
            query=normalized_query,
            terms=terms,
        )
        return PdfChunkSearchResult(
            query=normalized_query,
            matches=matches[:safe_limit],
            total_matches=len(matches),
            limit=safe_limit,
        )

    def _candidate_files(
        self,
        *,
        file_ids: list[str] | None,
        user_role: UserRole,
    ) -> list[PdfFile]:
        if file_ids:
            files: list[PdfFile] = []
            for file_id in _dedupe_file_ids(file_ids):
                file = self._repository.get_pdf_file(file_id)
                if file is None or not _is_visible_to_role(file, user_role):
                    raise AssetNotFoundError("PDF file was not found")
                if _is_searchable_file(file):
                    files.append(file)
            return files
        return [
            file
            for file in self._repository.list_pdf_files()
            if _is_visible_to_role(file, user_role) and _is_searchable_file(file)
        ]

    def _rank_matches(
        self,
        *,
        files: list[PdfFile],
        query: str,
        terms: list[str],
    ) -> list[PdfChunkSearchMatch]:
        matches: list[PdfChunkSearchMatch] = []
        for file in files:
            for chunk in self._repository.list_pdf_document_chunks(file.file_id):
                score, matched_terms = self._score_chunk(
                    chunk=chunk,
                    query=query,
                    terms=terms,
                )
                if score <= 0:
                    continue
                matches.append(
                    PdfChunkSearchMatch(
                        file=file,
                        chunk=chunk,
                        score=score,
                        excerpt=self._excerpt(chunk.text, query, matched_terms),
                        matched_terms=matched_terms,
                    )
                )
        return sorted(
            matches,
            key=lambda match: (
                -match.score,
                match.file.display_name.casefold(),
                match.chunk.chunk_index,
                match.chunk.chunk_id,
            ),
        )

    def _score_chunk(
        self,
        *,
        chunk: PdfDocumentChunk,
        query: str,
        terms: list[str],
    ) -> tuple[float, list[str]]:
        searchable_text = chunk.text.casefold()
        searchable_title = chunk.title.casefold()
        query_key = query.casefold()
        score = 0.0
        matched_terms: list[str] = []
        if query_key and query_key in searchable_text:
            score += self._policy.exact_query_weight
        for term in terms:
            text_hits = searchable_text.count(term)
            title_hits = searchable_title.count(term)
            if text_hits == 0 and title_hits == 0:
                continue
            matched_terms.append(term)
            score += text_hits + title_hits * self._policy.title_weight
        if len(matched_terms) == len(terms):
            score += 1.0
        return score, matched_terms

    def _excerpt(
        self,
        text: str,
        query: str,
        matched_terms: list[str],
    ) -> str:
        normalized_text = " ".join(text.split())
        if len(normalized_text) <= self._policy.excerpt_radius * 2:
            return normalized_text
        start_index = _first_match_index(normalized_text, [query, *matched_terms])
        if start_index < 0:
            return normalized_text[: self._policy.excerpt_radius * 2].strip()
        start = max(0, start_index - self._policy.excerpt_radius)
        end = min(len(normalized_text), start_index + self._policy.excerpt_radius)
        excerpt = normalized_text[start:end].strip()
        if start > 0:
            excerpt = f"...{excerpt}"
        if end < len(normalized_text):
            excerpt = f"{excerpt}..."
        return excerpt


def _dedupe_file_ids(file_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for file_id in file_ids:
        normalized = file_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _is_visible_to_role(file: PdfFile, user_role: UserRole) -> bool:
    return user_role == UserRole.ADMIN or file.visibility == PdfFileVisibility.VISIBLE


def _is_searchable_file(file: PdfFile) -> bool:
    return (
        file.kind == PdfFileKind.PDF
        and file.processing_status == PdfProcessingStatus.READY
    )


def _first_match_index(text: str, values: list[str]) -> int:
    searchable_text = text.casefold()
    indexes = [
        index
        for value in values
        if value
        if (index := searchable_text.find(value.casefold())) >= 0
    ]
    return min(indexes) if indexes else -1
