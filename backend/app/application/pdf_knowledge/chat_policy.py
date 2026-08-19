from dataclasses import dataclass


@dataclass(frozen=True)
class PdfChatPolicy:
    max_routed_documents: int = 4
    vector_hits_per_document: int = 8
    full_document_context: bool = True
    max_answer_context_chunks: int = 160
    max_answer_context_characters: int = 120_000
    max_answer_context_tokens: int = 30_000
    max_single_chunk_characters: int = 12_000
    max_fallback_routing_characters: int = 4_000
    fallback_routing_sample_chunks: int = 12


DEFAULT_PDF_CHAT_POLICY = PdfChatPolicy()
