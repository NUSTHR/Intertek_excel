from dataclasses import dataclass

from app.application.pdf_knowledge.chat_policy import PdfChatPolicy
from app.application.pdf_knowledge.chat_scope import is_visible_ready_pdf
from app.application.pdf_knowledge.models import PdfGroundingChunk
from app.core.errors import PdfAnswerContextTooLarge
from app.domain.models import SelectedDocument, UserRole
from app.ports.repository import PdfChatRepository


@dataclass(frozen=True)
class PdfContextAllocation:
    chunks: list[PdfGroundingChunk]
    truncated: bool
    used_characters: int
    used_tokens: int
    document_chunk_counts: dict[str, int]


class PdfContextAssembler:
    def __init__(
        self,
        *,
        repository: PdfChatRepository,
        policy: PdfChatPolicy,
    ) -> None:
        self._repository = repository
        self._policy = policy

    def assemble(
        self,
        *,
        documents: list[SelectedDocument],
        user_role: UserRole,
    ) -> PdfContextAllocation:
        requested_file_ids = [document.file_id for document in documents]
        files = {
            file.file_id: file
            for file in self._repository.list_pdf_files_by_ids(requested_file_ids)
            if is_visible_ready_pdf(file, user_role)
        }
        chunks_by_file_id = self._repository.list_pdf_document_chunks_by_file_ids(
            list(files)
        )
        chunks_by_document: list[list[PdfGroundingChunk]] = []
        total_available_chunks = 0
        total_available_characters = 0
        total_available_tokens = 0
        for document in documents:
            file = files.get(document.file_id)
            if file is None:
                continue
            document_chunks = [
                PdfGroundingChunk(
                    file=file,
                    chunk=chunk,
                    excerpt=chunk_excerpt(chunk.text),
                )
                for chunk in chunks_by_file_id.get(file.file_id, [])
            ]
            if document_chunks:
                chunks_by_document.append(document_chunks)
                total_available_chunks += len(document_chunks)
                total_available_characters += sum(
                    len(item.chunk.text) for item in document_chunks
                )
                total_available_tokens += sum(
                    item.chunk.token_count for item in document_chunks
                )

        if self._policy.full_document_context and (
            total_available_chunks > self._policy.max_answer_context_chunks
            or total_available_characters
            > self._policy.max_answer_context_characters
            or total_available_tokens > self._policy.max_answer_context_tokens
        ):
            raise PdfAnswerContextTooLarge(
                chunk_count=total_available_chunks,
                character_count=total_available_characters,
                token_count=total_available_tokens,
                max_chunks=self._policy.max_answer_context_chunks,
                max_characters=self._policy.max_answer_context_characters,
                max_tokens=self._policy.max_answer_context_tokens,
            )

        grounding_chunks: list[PdfGroundingChunk] = []
        used_characters = 0
        used_tokens = 0
        document_chunk_counts: dict[str, int] = {}
        chunk_index = 0
        while chunks_by_document:
            added_in_round = False
            for document_chunks in chunks_by_document:
                if chunk_index >= len(document_chunks):
                    continue
                item = document_chunks[chunk_index]
                payload_characters = (
                    len(item.chunk.text)
                    if self._policy.full_document_context
                    else min(
                        len(item.chunk.text),
                        self._policy.max_single_chunk_characters,
                    )
                )
                payload_tokens = (
                    item.chunk.token_count
                    if self._policy.full_document_context
                    else min(
                        item.chunk.token_count,
                        max(1, payload_characters // 4),
                    )
                )
                if (
                    not self._policy.full_document_context
                    and (
                        len(grounding_chunks)
                        >= self._policy.max_answer_context_chunks
                        or (
                            grounding_chunks
                            and used_characters + payload_characters
                            > self._policy.max_answer_context_characters
                        )
                        or (
                            grounding_chunks
                            and used_tokens + payload_tokens
                            > self._policy.max_answer_context_tokens
                        )
                    )
                ):
                    return PdfContextAllocation(
                        chunks=grounding_chunks,
                        truncated=True,
                        used_characters=used_characters,
                        used_tokens=used_tokens,
                        document_chunk_counts=document_chunk_counts,
                    )
                grounding_chunks.append(item)
                used_characters += payload_characters
                used_tokens += payload_tokens
                document_chunk_counts[item.file.file_id] = (
                    document_chunk_counts.get(item.file.file_id, 0) + 1
                )
                added_in_round = True
            if not added_in_round:
                break
            chunk_index += 1
        return PdfContextAllocation(
            chunks=grounding_chunks,
            truncated=len(grounding_chunks) < total_available_chunks,
            used_characters=used_characters,
            used_tokens=used_tokens,
            document_chunk_counts=document_chunk_counts,
        )


def chunk_excerpt(text: str, radius: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= radius:
        return normalized
    return f"{normalized[:radius].strip()}..."
