from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class WorkbookSheet:
    sheet_index: int
    sheet_name: str
    rows: list[list[str]]


@dataclass(frozen=True)
class WorkbookData:
    sheets: list[WorkbookSheet]


class WorkbookReader(Protocol):
    def read(self, path: Path) -> WorkbookData:
        ...
