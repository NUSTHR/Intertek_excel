from pathlib import Path

from app.adapters.pdf.mineru_parser import MinerUPdfParser


def test_mineru_parser_reads_markdown_output_and_metadata(tmp_path: Path) -> None:
    output_dir = tmp_path / "mineru-output"
    output_dir.mkdir()
    (output_dir / "document.md").write_text(
        "# Safety Manual\n\nCompliance evidence must be traceable.\n\n"
        "Testing records should be retained.",
        encoding="utf-8",
    )
    (output_dir / "metadata.json").write_text(
        '{"page_count": 3, "language": "en"}',
        encoding="utf-8",
    )
    parser = MinerUPdfParser(command="mineru")

    parsed = parser._read_output(filename="manual.pdf", output_dir=output_dir)

    assert parsed.page_count == 3
    assert parsed.chunk_count == 3
    assert parsed.preview_blocks[0].title == "Safety Manual"
    assert parsed.chunks[1].text == "Compliance evidence must be traceable."
    assert parsed.schema["Output Files"] == "2"
    assert "#mineru" in parsed.tags


def test_mineru_parser_extracts_text_from_json_when_markdown_is_missing(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "mineru-output"
    output_dir.mkdir()
    (output_dir / "middle.json").write_text(
        """
        {
          "pages": [
            {"page": 1, "content": "First JSON paragraph for extracted content."},
            {"page": 2, "text": "Second JSON paragraph for extracted content."}
          ],
          "total_pages": 2
        }
        """,
        encoding="utf-8",
    )
    parser = MinerUPdfParser(command="mineru")

    parsed = parser._read_output(filename="json-only.pdf", output_dir=output_dir)

    assert parsed.page_count == 2
    assert parsed.chunk_count == 2
    assert parsed.chunks[0].text == "First JSON paragraph for extracted content."
    assert parsed.chunks[1].text == "Second JSON paragraph for extracted content."


def test_mineru_parser_splits_oversized_text_chunks(tmp_path: Path) -> None:
    output_dir = tmp_path / "mineru-output"
    output_dir.mkdir()
    long_paragraph = " ".join(
        f"Sentence {index} contains enough content for stable chunking."
        for index in range(120)
    )
    (output_dir / "document.md").write_text(long_paragraph, encoding="utf-8")
    parser = MinerUPdfParser(command="mineru")

    parsed = parser._read_output(filename="long.pdf", output_dir=output_dir)

    assert parsed.chunk_count > 1
    assert all(len(chunk.text) <= 1_600 for chunk in parsed.chunks)
