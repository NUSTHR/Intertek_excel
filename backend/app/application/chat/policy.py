from dataclasses import dataclass

DEFAULT_MAX_ROUTED_DOCUMENTS = 3
DEFAULT_ROW_PAGE_SIZE = 5000
DEFAULT_MAX_ANSWER_ROWS = 20_000


@dataclass(frozen=True)
class ChatServicePolicy:
    max_routed_documents: int = DEFAULT_MAX_ROUTED_DOCUMENTS
    row_page_size: int = DEFAULT_ROW_PAGE_SIZE
    max_answer_rows: int = DEFAULT_MAX_ANSWER_ROWS

    @property
    def effective_max_answer_rows(self) -> int | None:
        return self.max_answer_rows if self.max_answer_rows > 0 else None
