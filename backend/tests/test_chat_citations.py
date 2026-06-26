from app.application.chat.citations import CitationVerifier
from app.domain.models import DraftCitation, ExcelCitation


def test_citation_verifier_uses_evidence_id_to_keep_correct_file() -> None:
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        ),
        "version_b::sheet_b::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_b::sheet_b::S001_R5",
            file_id="file_b",
            version_id="version_b",
            sheet_id="sheet_b",
            sheet_name="Sheet B",
            row_id="S001_R5",
            row=["S001_R5", "B row"],
        ),
    }

    result = CitationVerifier().build_verified_citations(
        [
            DraftCitation(
                evidence_id="version_a::sheet_a::S001_R5",
                quote="A row",
            )
        ],
        ["version_a::sheet_a::S001_R5"],
        citation_index,
    )

    assert result.warnings == []
    assert result.evidence_id_to_citation_id == {"version_a::sheet_a::S001_R5": "C1"}
    assert result.citations[0].file_id == "file_a"
    assert result.citations[0].sheet_id == "sheet_a"
    assert result.citations[0].row_id == "S001_R5"


def test_citation_verifier_rejects_ambiguous_legacy_row_id() -> None:
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        ),
        "version_b::sheet_b::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_b::sheet_b::S001_R5",
            file_id="file_b",
            version_id="version_b",
            sheet_id="sheet_b",
            sheet_name="Sheet B",
            row_id="S001_R5",
            row=["S001_R5", "B row"],
        ),
    }

    result = CitationVerifier().build_verified_citations(
        [DraftCitation(row_id="S001_R5", quote="legacy row id only")],
        ["S001_R5"],
        citation_index,
    )

    assert result.citations == []
    assert result.evidence_id_to_citation_id == {}
    assert "ignored ambiguous citation row_id: S001_R5" in result.warnings


def test_citation_verifier_rejects_invalid_evidence_id() -> None:
    citation_index = {
        "version_a::sheet_a::S001_R5": ExcelCitation(
            citation_id="",
            evidence_id="version_a::sheet_a::S001_R5",
            file_id="file_a",
            version_id="version_a",
            sheet_id="sheet_a",
            sheet_name="Sheet A",
            row_id="S001_R5",
            row=["S001_R5", "A row"],
        )
    }

    result = CitationVerifier().build_verified_citations(
        [DraftCitation(evidence_id="version_x::sheet_y::S001_R5", quote="bad")],
        ["version_x::sheet_y::S001_R5"],
        citation_index,
    )

    assert result.citations == []
    assert result.evidence_id_to_citation_id == {}
    assert (
        "ignored invalid citation evidence_id: version_x::sheet_y::S001_R5"
        in result.warnings
    )
