import sys

from app.core.config import Settings
from app.ports.pdf_retrieval import PdfRerankScore, PdfVectorChunkHit
from scripts import preflight_pdf_retrieval as preflight


def test_preflight_wires_qdrant_and_model_gateway_contracts(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    class Qdrant:
        def __init__(
            self,
            *,
            api_base_url: str,
            api_key: str,
            collection_name: str,
            embedding_dimension: int,
            timeout_seconds: float,
            auto_bootstrap: bool,
        ) -> None:
            assert api_base_url
            assert collection_name
            assert embedding_dimension == 4096
            assert timeout_seconds > 0
            assert auto_bootstrap is True
            assert api_key == ""

        def collection_exists(self) -> bool:
            return False

        def ensure_ready(self) -> None:
            return None

        def replace_document_revision(self, **kwargs) -> None:
            self.point = kwargs["points"][0]

        def search_document_chunks(self, **_kwargs) -> list[PdfVectorChunkHit]:
            return [
                PdfVectorChunkHit(
                    file_id=self.point.file_id,
                    chunk_id=self.point.chunk_id,
                    chunk_index=0,
                    score=1.0,
                    source_fingerprint=self.point.source_fingerprint,
                    embedding_revision=self.point.embedding_revision,
                )
            ]

        def delete_document_revision(self, **_kwargs) -> None:
            return None

    class Embedding:
        def __init__(
            self,
            *,
            api_base_url: str,
            api_key: str,
            model: str,
            revision: str,
            embedding_dimension: int,
            timeout_seconds: float,
            batch_size: int,
            max_input_characters: int,
        ) -> None:
            assert api_base_url and api_key and model and revision
            assert embedding_dimension == 4096
            assert timeout_seconds > 0 and batch_size > 0
            assert max_input_characters > 0

        def embed_query(self, _text: str) -> tuple[float, ...]:
            return (0.0,) * 4096

    class Reranker:
        def __init__(
            self,
            *,
            api_base_url: str,
            api_key: str,
            model: str,
            revision: str,
            timeout_seconds: float,
            batch_size: int,
            max_batch_characters: int,
        ) -> None:
            assert api_base_url and api_key and model and revision
            assert timeout_seconds > 0 and batch_size > 0
            assert max_batch_characters > 0

        def rank_documents(self, *, query: str, documents) -> list[PdfRerankScore]:
            assert query and len(documents) == 2
            return [
                PdfRerankScore(file_id=document.file_id, score=1.0)
                for document in documents
            ]

    settings = Settings(
        excel_database_path=str(tmp_path / "preflight.sqlite3"),
        llm_api_key="test-key",
        pdf_vector_indexing_enabled=True,
        pdf_vector_ranking_enabled=True,
        pdf_qdrant_auto_bootstrap=True,
    )
    monkeypatch.setattr(preflight, "Settings", lambda: settings)
    monkeypatch.setattr(preflight, "QdrantPdfVectorStore", Qdrant)
    monkeypatch.setattr(preflight, "OpenAiCompatiblePdfEmbeddingGateway", Embedding)
    monkeypatch.setattr(preflight, "HttpPdfRerankerGateway", Reranker)
    monkeypatch.setattr(sys, "argv", ["preflight", "--bootstrap-qdrant"])

    assert preflight.main() == 0
    assert '"status": "ok"' in capsys.readouterr().out
