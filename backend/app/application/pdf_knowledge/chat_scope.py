from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import AssetNotFoundError
from app.domain.models import (
    PdfFile,
    PdfFileKind,
    PdfFileVisibility,
    PdfProcessingStatus,
    UserRole,
)
from app.ports.repository import PdfChatRepository


class PdfChatScopeMode(StrEnum):
    ALL_SOURCES = "all_sources"
    SELECTED_NODES = "selected_nodes"


@dataclass(frozen=True)
class PdfChatScope:
    mode: PdfChatScopeMode
    selected_node_ids: list[str]


@dataclass(frozen=True)
class ResolvedPdfChatScope:
    scope: PdfChatScope
    candidate_file_ids: list[str]

    @property
    def has_explicit_scope(self) -> bool:
        return self.scope.mode == PdfChatScopeMode.SELECTED_NODES


class PdfChatScopeResolver:
    def __init__(self, repository: PdfChatRepository) -> None:
        self._repository = repository

    def resolve(
        self,
        *,
        selected_node_ids: list[str] | None,
        user_role: UserRole,
    ) -> ResolvedPdfChatScope:
        normalized_node_ids = dedupe_file_ids(selected_node_ids or [])
        files = self._repository.list_pdf_files()
        if not normalized_node_ids:
            return ResolvedPdfChatScope(
                scope=PdfChatScope(
                    mode=PdfChatScopeMode.ALL_SOURCES,
                    selected_node_ids=[],
                ),
                candidate_file_ids=[
                    file.file_id
                    for file in files
                    if is_visible_ready_pdf(file, user_role)
                ],
            )

        files_by_id = {file.file_id: file for file in files}
        selected: list[PdfFile] = []
        for node_id in normalized_node_ids:
            file = files_by_id.get(node_id)
            if file is None or not is_visible_pdf_scope(file, user_role):
                raise AssetNotFoundError("PDF file was not found")
            if file.kind == PdfFileKind.FOLDER:
                selected.extend(
                    descendant_ready_pdf_files(
                        file.file_id,
                        files_by_id,
                        user_role,
                    )
                )
                continue
            if is_visible_ready_pdf(file, user_role):
                selected.append(file)

        return ResolvedPdfChatScope(
            scope=PdfChatScope(
                mode=PdfChatScopeMode.SELECTED_NODES,
                selected_node_ids=normalized_node_ids,
            ),
            candidate_file_ids=dedupe_file_ids([file.file_id for file in selected]),
        )


def dedupe_file_ids(file_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for file_id in file_ids:
        normalized = file_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def is_visible_ready_pdf(file: PdfFile, user_role: UserRole) -> bool:
    return (
        file.kind == PdfFileKind.PDF
        and file.processing_status == PdfProcessingStatus.READY
        and (
            user_role == UserRole.ADMIN
            or file.visibility == PdfFileVisibility.VISIBLE
        )
    )


def is_visible_pdf_scope(file: PdfFile, user_role: UserRole) -> bool:
    return user_role == UserRole.ADMIN or file.visibility == PdfFileVisibility.VISIBLE


def descendant_ready_pdf_files(
    parent_id: str,
    files_by_id: dict[str, PdfFile],
    user_role: UserRole,
) -> list[PdfFile]:
    children_by_parent: dict[str | None, list[PdfFile]] = {}
    for file in files_by_id.values():
        children_by_parent.setdefault(file.parent_id, []).append(file)
    descendants: list[PdfFile] = []
    stack = list(children_by_parent.get(parent_id, []))
    while stack:
        file = stack.pop(0)
        if file.kind == PdfFileKind.PDF:
            if is_visible_ready_pdf(file, user_role):
                descendants.append(file)
            continue
        if file.kind == PdfFileKind.FOLDER and is_visible_pdf_scope(file, user_role):
            stack.extend(children_by_parent.get(file.file_id, []))
    return descendants
