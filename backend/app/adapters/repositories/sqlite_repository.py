import json
import sqlite3
from pathlib import Path

from app.domain.models import (
    AttachedDocument,
    ChatSession,
    ChatTurn,
    DocumentSummary,
    ExcelArtifact,
    ExcelArtifactType,
    ExcelFile,
    ExcelFileVersion,
    ExcelRowMapping,
    ExcelSheet,
    ExcelVersionStatus,
    SelectedDocument,
    SheetSummary,
)


class SQLiteExcelAssetRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS excel_files (
                  file_id TEXT PRIMARY KEY,
                  display_name TEXT NOT NULL UNIQUE,
                  active_version_id TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS excel_file_versions (
                  version_id TEXT PRIMARY KEY,
                  file_id TEXT NOT NULL,
                  original_filename TEXT NOT NULL,
                  file_hash TEXT NOT NULL,
                  status TEXT NOT NULL,
                  error_message TEXT,
                  created_at TEXT NOT NULL,
                  activated_at TEXT,
                  FOREIGN KEY(file_id) REFERENCES excel_files(file_id)
                );

                CREATE TABLE IF NOT EXISTS excel_sheets (
                  sheet_id TEXT PRIMARY KEY,
                  version_id TEXT NOT NULL,
                  sheet_index INTEGER NOT NULL,
                  sheet_code TEXT NOT NULL,
                  sheet_name TEXT NOT NULL,
                  row_count INTEGER NOT NULL,
                  column_count INTEGER NOT NULL,
                  raw_csv_path TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS excel_artifacts (
                  artifact_id TEXT PRIMARY KEY,
                  version_id TEXT NOT NULL,
                  artifact_type TEXT NOT NULL,
                  path TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS excel_row_mappings (
                  mapping_id TEXT PRIMARY KEY,
                  version_id TEXT NOT NULL,
                  sheet_id TEXT NOT NULL,
                  row_id TEXT NOT NULL,
                  original_row_number INTEGER NOT NULL,
                  raw_csv_row_number INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id),
                  FOREIGN KEY(sheet_id) REFERENCES excel_sheets(sheet_id),
                  UNIQUE(sheet_id, row_id)
                );

                CREATE TABLE IF NOT EXISTS document_summaries (
                  summary_id TEXT PRIMARY KEY,
                  file_id TEXT NOT NULL,
                  version_id TEXT NOT NULL UNIQUE,
                  summary_text TEXT NOT NULL,
                  business_domain TEXT NOT NULL,
                  key_topics_json TEXT NOT NULL,
                  suitable_questions_json TEXT NOT NULL,
                  unsuitable_questions_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS document_sheet_summaries (
                  summary_id TEXT NOT NULL,
                  sheet_id TEXT NOT NULL,
                  sheet_name TEXT NOT NULL,
                  summary TEXT NOT NULL,
                  important_columns_json TEXT NOT NULL,
                  likely_question_types_json TEXT NOT NULL,
                  PRIMARY KEY(summary_id, sheet_id),
                  FOREIGN KEY(summary_id) REFERENCES document_summaries(summary_id)
                );

                CREATE TABLE IF NOT EXISTS chat_sessions (
                  session_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_session_documents (
                  session_id TEXT NOT NULL,
                  file_id TEXT NOT NULL,
                  version_id TEXT NOT NULL,
                  attached_at TEXT NOT NULL,
                  row_count INTEGER NOT NULL,
                  context_hash TEXT NOT NULL,
                  status TEXT NOT NULL,
                  PRIMARY KEY(session_id, version_id),
                  FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id),
                  FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
                );

                CREATE TABLE IF NOT EXISTS chat_turns (
                  turn_id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  question TEXT NOT NULL,
                  answer_text TEXT NOT NULL,
                  citation_ids_json TEXT NOT NULL,
                  selected_documents_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_versions_file_id
                  ON excel_file_versions(file_id);
                CREATE INDEX IF NOT EXISTS idx_sheets_version_id
                  ON excel_sheets(version_id);
                CREATE INDEX IF NOT EXISTS idx_mappings_sheet_row
                  ON excel_row_mappings(sheet_id, row_id);
                CREATE INDEX IF NOT EXISTS idx_sheet_summaries_summary_id
                  ON document_sheet_summaries(summary_id);
                CREATE INDEX IF NOT EXISTS idx_chat_turns_session_id
                  ON chat_turns(session_id, created_at);
                """
            )

    def create_file(self, file: ExcelFile) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_files
                  (file_id, display_name, active_version_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    file.file_id,
                    file.display_name,
                    file.active_version_id,
                    file.created_at,
                    file.updated_at,
                ),
            )

    def get_file(self, file_id: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_files WHERE file_id = ?",
                (file_id,),
            ).fetchone()
        return self._to_file(row)

    def find_file_by_display_name(self, display_name: str) -> ExcelFile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_files WHERE display_name = ?",
                (display_name,),
            ).fetchone()
        return self._to_file(row)

    def list_files(self) -> list[ExcelFile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM excel_files ORDER BY updated_at DESC, display_name ASC"
            ).fetchall()
        return [file for row in rows if (file := self._to_file(row)) is not None]

    def delete_file(self, file_id: str) -> dict[str, int]:
        with self._connect() as connection:
            version_rows = connection.execute(
                """
                SELECT version_id FROM excel_file_versions
                WHERE file_id = ?
                """,
                (file_id,),
            ).fetchall()
            version_ids = [str(row["version_id"]) for row in version_rows]

            deleted_chat_session_documents = 0
            deleted_summaries = 0
            deleted_row_mappings = 0
            deleted_artifacts = 0
            deleted_sheets = 0
            deleted_versions = 0

            if version_ids:
                placeholders = ",".join("?" for _ in version_ids)

                deleted_chat_session_documents = connection.execute(
                    f"""
                    DELETE FROM chat_session_documents
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount

                summary_ids = connection.execute(
                    f"""
                    SELECT summary_id FROM document_summaries
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).fetchall()
                if summary_ids:
                    summary_id_values = [str(row["summary_id"]) for row in summary_ids]
                    summary_placeholders = ",".join("?" for _ in summary_id_values)
                    connection.execute(
                        f"""
                        DELETE FROM document_sheet_summaries
                        WHERE summary_id IN ({summary_placeholders})
                        """,
                        summary_id_values,
                    )
                deleted_summaries = connection.execute(
                    f"""
                    DELETE FROM document_summaries
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount

                sheet_rows = connection.execute(
                    f"""
                    SELECT sheet_id FROM excel_sheets
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).fetchall()
                sheet_ids = [str(row["sheet_id"]) for row in sheet_rows]
                if sheet_ids:
                    sheet_placeholders = ",".join("?" for _ in sheet_ids)
                    deleted_row_mappings = connection.execute(
                        f"""
                        DELETE FROM excel_row_mappings
                        WHERE sheet_id IN ({sheet_placeholders})
                        """,
                        sheet_ids,
                    ).rowcount

                deleted_artifacts = connection.execute(
                    f"""
                    DELETE FROM excel_artifacts
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount
                deleted_sheets = connection.execute(
                    f"""
                    DELETE FROM excel_sheets
                    WHERE version_id IN ({placeholders})
                    """,
                    version_ids,
                ).rowcount
                deleted_versions = connection.execute(
                    """
                    DELETE FROM excel_file_versions
                    WHERE file_id = ?
                    """,
                    (file_id,),
                ).rowcount

            connection.execute(
                """
                UPDATE excel_files
                SET active_version_id = NULL
                WHERE file_id = ?
                """,
                (file_id,),
            )
            connection.execute(
                """
                DELETE FROM chat_turns
                WHERE session_id IN (
                  SELECT session_id FROM chat_sessions
                  WHERE session_id NOT IN (
                    SELECT DISTINCT session_id FROM chat_session_documents
                  )
                )
                """
            )
            connection.execute(
                """
                DELETE FROM chat_sessions
                WHERE session_id NOT IN (
                  SELECT DISTINCT session_id FROM chat_turns
                )
                AND session_id NOT IN (
                  SELECT DISTINCT session_id FROM chat_session_documents
                )
                """
            )
            connection.execute(
                """
                DELETE FROM excel_files
                WHERE file_id = ?
                """,
                (file_id,),
            )

        return {
            "deleted_versions": deleted_versions,
            "deleted_sheets": deleted_sheets,
            "deleted_artifacts": deleted_artifacts,
            "deleted_row_mappings": deleted_row_mappings,
            "deleted_summaries": deleted_summaries,
            "deleted_chat_session_documents": deleted_chat_session_documents,
        }

    def create_version(self, version: ExcelFileVersion) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_file_versions
                  (
                    version_id, file_id, original_filename, file_hash, status,
                    error_message, created_at, activated_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.file_id,
                    version.original_filename,
                    version.file_hash,
                    version.status.value,
                    version.error_message,
                    version.created_at,
                    version.activated_at,
                ),
            )

    def get_version(self, version_id: str) -> ExcelFileVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_file_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
        return self._to_version(row)

    def list_versions(self, file_id: str) -> list[ExcelFileVersion]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_file_versions
                WHERE file_id = ?
                ORDER BY created_at DESC
                """,
                (file_id,),
            ).fetchall()
        return [version for row in rows if (version := self._to_version(row)) is not None]

    def update_version_status(
        self,
        version_id: str,
        status: ExcelVersionStatus,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE excel_file_versions
                SET status = ?, error_message = ?
                WHERE version_id = ?
                """,
                (status.value, error_message, version_id),
            )

    def activate_version(self, file_id: str, version_id: str, activated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE excel_files
                SET active_version_id = ?, updated_at = ?
                WHERE file_id = ?
                """,
                (version_id, activated_at, file_id),
            )
            connection.execute(
                """
                UPDATE excel_file_versions
                SET status = ?, activated_at = ?
                WHERE version_id = ?
                """,
                (ExcelVersionStatus.READY.value, activated_at, version_id),
            )

    def create_sheet(self, sheet: ExcelSheet) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_sheets
                  (
                    sheet_id, version_id, sheet_index, sheet_code, sheet_name,
                    row_count, column_count, raw_csv_path, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sheet.sheet_id,
                    sheet.version_id,
                    sheet.sheet_index,
                    sheet.sheet_code,
                    sheet.sheet_name,
                    sheet.row_count,
                    sheet.column_count,
                    sheet.raw_csv_path,
                    sheet.created_at,
                ),
            )

    def get_sheet(self, sheet_id: str) -> ExcelSheet | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM excel_sheets WHERE sheet_id = ?",
                (sheet_id,),
            ).fetchone()
        return self._to_sheet(row)

    def list_sheets(self, version_id: str) -> list[ExcelSheet]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_sheets
                WHERE version_id = ?
                ORDER BY sheet_index ASC
                """,
                (version_id,),
            ).fetchall()
        return [sheet for row in rows if (sheet := self._to_sheet(row)) is not None]

    def create_artifact(self, artifact: ExcelArtifact) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO excel_artifacts
                  (artifact_id, version_id, artifact_type, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.version_id,
                    artifact.artifact_type.value,
                    artifact.path,
                    artifact.created_at,
                ),
            )

    def list_artifacts(self, version_id: str) -> list[ExcelArtifact]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_artifacts
                WHERE version_id = ?
                ORDER BY created_at ASC
                """,
                (version_id,),
            ).fetchall()
        return [artifact for row in rows if (artifact := self._to_artifact(row)) is not None]

    def create_row_mappings(self, mappings: list[ExcelRowMapping]) -> None:
        if not mappings:
            return
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO excel_row_mappings
                  (
                    mapping_id, version_id, sheet_id, row_id,
                    original_row_number, raw_csv_row_number, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        mapping.mapping_id,
                        mapping.version_id,
                        mapping.sheet_id,
                        mapping.row_id,
                        mapping.original_row_number,
                        mapping.raw_csv_row_number,
                        mapping.created_at,
                    )
                    for mapping in mappings
                ],
            )

    def get_row_mapping(
        self,
        sheet_id: str,
        row_id: str,
    ) -> ExcelRowMapping | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM excel_row_mappings
                WHERE sheet_id = ? AND row_id = ?
                """,
                (sheet_id, row_id),
            ).fetchone()
        return self._to_mapping(row)

    def list_row_mappings_for_sheet(self, sheet_id: str) -> list[ExcelRowMapping]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM excel_row_mappings
                WHERE sheet_id = ?
                ORDER BY raw_csv_row_number ASC
                """,
                (sheet_id,),
            ).fetchall()
        return [mapping for row in rows if (mapping := self._to_mapping(row)) is not None]

    def save_summary(self, summary: DocumentSummary) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM document_sheet_summaries
                WHERE summary_id IN (
                  SELECT summary_id FROM document_summaries WHERE version_id = ?
                )
                """,
                (summary.version_id,),
            )
            connection.execute(
                "DELETE FROM document_summaries WHERE version_id = ?",
                (summary.version_id,),
            )
            connection.execute(
                """
                INSERT INTO document_summaries
                  (
                    summary_id, file_id, version_id, summary_text, business_domain,
                    key_topics_json, suitable_questions_json,
                    unsuitable_questions_json, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.summary_id,
                    summary.file_id,
                    summary.version_id,
                    summary.summary_text,
                    summary.business_domain,
                    self._dump_json(summary.key_topics),
                    self._dump_json(summary.suitable_questions),
                    self._dump_json(summary.unsuitable_questions),
                    summary.created_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO document_sheet_summaries
                  (
                    summary_id, sheet_id, sheet_name, summary,
                    important_columns_json, likely_question_types_json
                  )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.summary_id,
                        sheet.sheet_id,
                        sheet.sheet_name,
                        sheet.summary,
                        self._dump_json(sheet.important_columns),
                        self._dump_json(sheet.likely_question_types),
                    )
                    for sheet in summary.sheet_summaries
                ],
            )

    def get_summary(self, version_id: str) -> DocumentSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_summaries WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if row is None:
                return None
            sheet_rows = connection.execute(
                """
                SELECT * FROM document_sheet_summaries
                WHERE summary_id = ?
                ORDER BY rowid ASC
                """,
                (row["summary_id"],),
            ).fetchall()
        return self._to_summary(row, sheet_rows)

    def list_summaries(self) -> list[DocumentSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM document_summaries ORDER BY created_at DESC"
            ).fetchall()
            sheet_rows_by_summary_id = {
                str(row["summary_id"]): connection.execute(
                    """
                    SELECT * FROM document_sheet_summaries
                    WHERE summary_id = ?
                    ORDER BY rowid ASC
                    """,
                    (row["summary_id"],),
                ).fetchall()
                for row in rows
            }
        return [
            summary
            for row in rows
            if (
                summary := self._to_summary(
                    row,
                    sheet_rows_by_summary_id.get(str(row["summary_id"]), []),
                )
            )
            is not None
        ]

    def create_session(self, session: ChatSession) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_sessions
                  (session_id, created_at, updated_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.created_at,
                    session.updated_at,
                    session.status,
                ),
            )

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._to_session(row)

    def touch_session(self, session_id: str, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?
                WHERE session_id = ?
                """,
                (updated_at, session_id),
            )

    def attach_document(self, document: AttachedDocument) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_session_documents
                  (
                    session_id, file_id, version_id, attached_at,
                    row_count, context_hash, status
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.session_id,
                    document.file_id,
                    document.version_id,
                    document.attached_at,
                    document.row_count,
                    document.context_hash,
                    document.status,
                ),
            )

    def list_attached_documents(self, session_id: str) -> list[AttachedDocument]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_session_documents
                WHERE session_id = ?
                ORDER BY attached_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [doc for row in rows if (doc := self._to_attached_document(row)) is not None]

    def create_turn(self, turn: ChatTurn) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_turns
                  (
                    turn_id, session_id, question, answer_text,
                    citation_ids_json, selected_documents_json, created_at
                  )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.session_id,
                    turn.question,
                    turn.answer_text,
                    self._dump_json(turn.citation_ids),
                    self._dump_json(
                        [
                            {
                                "file_id": document.file_id,
                                "version_id": document.version_id,
                                "reason": document.reason,
                                "confidence": document.confidence,
                            }
                            for document in turn.selected_documents
                        ]
                    ),
                    turn.created_at,
                ),
            )

    def list_turns(self, session_id: str) -> list[ChatTurn]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_turns
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [turn for row in rows if (turn := self._to_turn(row)) is not None]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _to_file(self, row: sqlite3.Row | None) -> ExcelFile | None:
        if row is None:
            return None
        return ExcelFile(
            file_id=str(row["file_id"]),
            display_name=str(row["display_name"]),
            active_version_id=row["active_version_id"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _to_version(self, row: sqlite3.Row | None) -> ExcelFileVersion | None:
        if row is None:
            return None
        return ExcelFileVersion(
            version_id=str(row["version_id"]),
            file_id=str(row["file_id"]),
            original_filename=str(row["original_filename"]),
            file_hash=str(row["file_hash"]),
            status=ExcelVersionStatus(str(row["status"])),
            error_message=row["error_message"],
            created_at=str(row["created_at"]),
            activated_at=row["activated_at"],
        )

    def _to_sheet(self, row: sqlite3.Row | None) -> ExcelSheet | None:
        if row is None:
            return None
        return ExcelSheet(
            sheet_id=str(row["sheet_id"]),
            version_id=str(row["version_id"]),
            sheet_index=int(row["sheet_index"]),
            sheet_code=str(row["sheet_code"]),
            sheet_name=str(row["sheet_name"]),
            row_count=int(row["row_count"]),
            column_count=int(row["column_count"]),
            raw_csv_path=str(row["raw_csv_path"]),
            created_at=str(row["created_at"]),
        )

    def _to_artifact(self, row: sqlite3.Row | None) -> ExcelArtifact | None:
        if row is None:
            return None
        return ExcelArtifact(
            artifact_id=str(row["artifact_id"]),
            version_id=str(row["version_id"]),
            artifact_type=ExcelArtifactType(str(row["artifact_type"])),
            path=str(row["path"]),
            created_at=str(row["created_at"]),
        )

    def _to_mapping(self, row: sqlite3.Row | None) -> ExcelRowMapping | None:
        if row is None:
            return None
        return ExcelRowMapping(
            mapping_id=str(row["mapping_id"]),
            version_id=str(row["version_id"]),
            sheet_id=str(row["sheet_id"]),
            row_id=str(row["row_id"]),
            original_row_number=int(row["original_row_number"]),
            raw_csv_row_number=int(row["raw_csv_row_number"]),
            created_at=str(row["created_at"]),
        )

    def _to_summary(
        self,
        row: sqlite3.Row | None,
        sheet_rows: list[sqlite3.Row],
    ) -> DocumentSummary | None:
        if row is None:
            return None
        return DocumentSummary(
            summary_id=str(row["summary_id"]),
            file_id=str(row["file_id"]),
            version_id=str(row["version_id"]),
            summary_text=str(row["summary_text"]),
            business_domain=str(row["business_domain"]),
            key_topics=self._load_string_list(row["key_topics_json"]),
            suitable_questions=self._load_string_list(row["suitable_questions_json"]),
            unsuitable_questions=self._load_string_list(
                row["unsuitable_questions_json"]
            ),
            sheet_summaries=[
                SheetSummary(
                    sheet_id=str(sheet_row["sheet_id"]),
                    sheet_name=str(sheet_row["sheet_name"]),
                    summary=str(sheet_row["summary"]),
                    important_columns=self._load_string_list(
                        sheet_row["important_columns_json"]
                    ),
                    likely_question_types=self._load_string_list(
                        sheet_row["likely_question_types_json"]
                    ),
                )
                for sheet_row in sheet_rows
            ],
            created_at=str(row["created_at"]),
        )

    def _to_session(self, row: sqlite3.Row | None) -> ChatSession | None:
        if row is None:
            return None
        return ChatSession(
            session_id=str(row["session_id"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            status=str(row["status"]),
        )

    def _to_attached_document(
        self,
        row: sqlite3.Row | None,
    ) -> AttachedDocument | None:
        if row is None:
            return None
        return AttachedDocument(
            session_id=str(row["session_id"]),
            file_id=str(row["file_id"]),
            version_id=str(row["version_id"]),
            attached_at=str(row["attached_at"]),
            row_count=int(row["row_count"]),
            context_hash=str(row["context_hash"]),
            status=str(row["status"]),
        )

    def _to_turn(self, row: sqlite3.Row | None) -> ChatTurn | None:
        if row is None:
            return None
        return ChatTurn(
            turn_id=str(row["turn_id"]),
            session_id=str(row["session_id"]),
            question=str(row["question"]),
            answer_text=str(row["answer_text"]),
            citation_ids=self._load_string_list(row["citation_ids_json"]),
            selected_documents=[
                SelectedDocument(
                    file_id=str(document.get("file_id", "")),
                    version_id=str(document.get("version_id", "")),
                    reason=str(document.get("reason", "")),
                    confidence=document.get("confidence"),
                )
                for document in self._load_object_list(row["selected_documents_json"])
            ],
            created_at=str(row["created_at"]),
        )

    def _dump_json(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _load_string_list(self, value: object) -> list[str]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if str(item).strip()]

    def _load_object_list(self, value: object) -> list[dict]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]
