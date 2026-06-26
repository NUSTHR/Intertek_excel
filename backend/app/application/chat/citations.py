from dataclasses import dataclass

from app.domain.models import ExcelCitation


@dataclass(frozen=True)
class VerifiedCitationResult:
    citations: list[ExcelCitation]
    evidence_id_to_citation_id: dict[str, str]
    warnings: list[str]


class CitationVerifier:
    def build_verified_citations(
        self,
        draft_citations: list,
        evidence_ids: list[str],
        citation_index: dict[str, ExcelCitation],
    ) -> VerifiedCitationResult:
        citations: list[ExcelCitation] = []
        evidence_id_to_citation_id: dict[str, str] = {}
        warnings: list[str] = []
        row_matches_by_row_id = self._row_matches_by_row_id(citation_index)
        quotes_by_evidence_id: dict[str, str] = {}
        for draft in draft_citations:
            resolved_evidence_id, warning = self._resolve_draft_citation_evidence_id(
                draft,
                citation_index,
                row_matches_by_row_id,
            )
            if warning is not None:
                warnings.append(warning)
                continue
            if resolved_evidence_id is None:
                continue
            quotes_by_evidence_id[resolved_evidence_id] = draft.quote

        for evidence_reference in [*quotes_by_evidence_id, *evidence_ids]:
            resolved_evidence_id, warning = self._resolve_evidence_reference(
                evidence_reference,
                citation_index,
                row_matches_by_row_id,
            )
            if warning is not None:
                warnings.append(warning)
                continue
            if resolved_evidence_id is None:
                continue
            source = citation_index.get(resolved_evidence_id)
            if source is None:
                warnings.append(
                    f"ignored invalid citation evidence_id: {resolved_evidence_id}"
                )
                continue
            if resolved_evidence_id in evidence_id_to_citation_id:
                continue
            citation_id = f"C{len(citations) + 1}"
            evidence_id_to_citation_id[resolved_evidence_id] = citation_id
            citations.append(
                ExcelCitation(
                    citation_id=citation_id,
                    evidence_id=source.evidence_id,
                    file_id=source.file_id,
                    version_id=source.version_id,
                    sheet_id=source.sheet_id,
                    sheet_name=source.sheet_name,
                    row_id=source.row_id,
                    row=source.row,
                    quote=quotes_by_evidence_id.get(resolved_evidence_id, ""),
                )
            )
        return VerifiedCitationResult(
            citations=citations,
            evidence_id_to_citation_id=evidence_id_to_citation_id,
            warnings=warnings,
        )

    def evidence_id(self, *, version_id: str, sheet_id: str, row_id: str) -> str:
        return f"{version_id}::{sheet_id}::{row_id}"

    def _row_matches_by_row_id(
        self,
        citation_index: dict[str, ExcelCitation],
    ) -> dict[str, list[ExcelCitation]]:
        matches: dict[str, list[ExcelCitation]] = {}
        for citation in citation_index.values():
            matches.setdefault(citation.row_id, []).append(citation)
        return matches

    def _resolve_draft_citation_evidence_id(
        self,
        draft_citation,
        citation_index: dict[str, ExcelCitation],
        row_matches_by_row_id: dict[str, list[ExcelCitation]],
    ) -> tuple[str | None, str | None]:
        if draft_citation.evidence_id:
            if draft_citation.evidence_id in citation_index:
                return draft_citation.evidence_id, None
            return (
                None,
                f"ignored invalid citation evidence_id: {draft_citation.evidence_id}",
            )
        if draft_citation.version_id and draft_citation.sheet_id and draft_citation.row_id:
            evidence_id = self.evidence_id(
                version_id=draft_citation.version_id,
                sheet_id=draft_citation.sheet_id,
                row_id=draft_citation.row_id,
            )
            if evidence_id in citation_index:
                return evidence_id, None
            return None, f"ignored invalid citation evidence_id: {evidence_id}"
        if draft_citation.row_id:
            return self._resolve_evidence_reference(
                draft_citation.row_id,
                citation_index,
                row_matches_by_row_id,
            )
        return None, None

    def _resolve_evidence_reference(
        self,
        evidence_reference: str,
        citation_index: dict[str, ExcelCitation],
        row_matches_by_row_id: dict[str, list[ExcelCitation]],
    ) -> tuple[str | None, str | None]:
        if evidence_reference in citation_index:
            return evidence_reference, None
        matches = row_matches_by_row_id.get(evidence_reference, [])
        if not matches:
            if "::" in evidence_reference:
                return (
                    None,
                    f"ignored invalid citation evidence_id: {evidence_reference}",
                )
            return None, f"ignored invalid citation row_id: {evidence_reference}"
        if len(matches) > 1:
            return None, f"ignored ambiguous citation row_id: {evidence_reference}"
        return matches[0].evidence_id, None
