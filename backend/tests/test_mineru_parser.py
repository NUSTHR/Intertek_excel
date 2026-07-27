from pathlib import Path
from subprocess import CompletedProcess

from app.adapters.pdf.mineru_parser import MinerUPdfParser, read_mineru_output


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


def test_mineru_parser_invokes_configured_cli_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("app.adapters.pdf.mineru_parser.subprocess.run", fake_run)
    parser = MinerUPdfParser(
        command="mineru",
        cli_backend="pipeline",
        extra_args=("--lang", "ch"),
    )

    parser._run_mineru(input_path=tmp_path / "input.pdf", output_dir=tmp_path / "output")

    assert commands == [
        [
            "mineru",
            "-p",
            str(tmp_path / "input.pdf"),
            "-o",
            str(tmp_path / "output"),
            "-b",
            "pipeline",
            "--lang",
            "ch",
        ]
    ]


def test_mineru_parser_summarizes_cli_import_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_run(command, **kwargs):
        return CompletedProcess(
            command,
            1,
            stdout="Started local mineru-api",
            stderr="Traceback...\nModuleNotFoundError: No module named 'torchvision'",
        )

    monkeypatch.setattr("app.adapters.pdf.mineru_parser.subprocess.run", fake_run)
    parser = MinerUPdfParser(command="mineru")

    try:
        parser._run_mineru(input_path=tmp_path / "input.pdf", output_dir=tmp_path / "output")
    except RuntimeError as exc:
        assert str(exc) == "MinerU parsing failed: No module named 'torchvision'"
    else:
        raise AssertionError("MinerU parser did not raise on a failed CLI run")


def test_read_mineru_output_accepts_custom_cloud_parser_metadata(tmp_path: Path) -> None:
    output_dir = tmp_path / "mineru-cloud-output"
    output_dir.mkdir()
    (output_dir / "full.md").write_text("# Cloud Result\n\nParsed by VLM.", encoding="utf-8")
    (output_dir / "full_middle.json").write_text('{"total_pages": 1}', encoding="utf-8")

    parsed = read_mineru_output(
        filename="cloud.pdf",
        output_dir=output_dir,
        parser_name="MinerU Cloud",
        parser_backend="mineru-cloud",
        parser_version="vlm",
        extra_warnings=["Cloud task completed with official v4 API."],
    )

    assert parsed.parser_backend == "mineru-cloud"
    assert parsed.parser_version == "vlm"
    assert parsed.schema["Parser"] == "MinerU Cloud"
    assert "Cloud task completed" in parsed.warnings[0]
