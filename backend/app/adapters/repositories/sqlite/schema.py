from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    statements: tuple[str, ...]


SCHEMA_MIGRATIONS: tuple[SchemaMigration, ...] = (
    SchemaMigration(
        version=1,
        name="initial_excel_workspace_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS excel_files (
              file_id TEXT PRIMARY KEY,
              display_name TEXT NOT NULL UNIQUE,
              active_version_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
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
            )
            """,
            """
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_artifacts (
              artifact_id TEXT PRIMARY KEY,
              version_id TEXT NOT NULL,
              artifact_type TEXT NOT NULL,
              path TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(version_id) REFERENCES excel_file_versions(version_id)
            )
            """,
            """
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
            )
            """,
            """
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_sheet_summaries (
              summary_id TEXT NOT NULL,
              sheet_id TEXT NOT NULL,
              sheet_name TEXT NOT NULL,
              summary TEXT NOT NULL,
              important_columns_json TEXT NOT NULL,
              likely_question_types_json TEXT NOT NULL,
              PRIMARY KEY(summary_id, sheet_id),
              FOREIGN KEY(summary_id) REFERENCES document_summaries(summary_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
              session_id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """,
            """
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_turns (
              turn_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              question TEXT NOT NULL,
              answer_text TEXT NOT NULL,
              citation_ids_json TEXT NOT NULL,
              selected_documents_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_versions_file_id
              ON excel_file_versions(file_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sheets_version_id
              ON excel_sheets(version_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_mappings_sheet_row
              ON excel_row_mappings(sheet_id, row_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_sheet_summaries_summary_id
              ON document_sheet_summaries(summary_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_turns_session_id
              ON chat_turns(session_id, created_at)
            """,
        ),
    ),
    SchemaMigration(
        version=2,
        name="add_chat_session_metadata",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN title TEXT NOT NULL DEFAULT 'New chat'
            """,
            """
            ALTER TABLE chat_sessions
            ADD COLUMN pinned_at TEXT
            """,
        ),
    ),
    SchemaMigration(
        version=3,
        name="add_document_routing_summary_fields",
        statements=(
            """
            ALTER TABLE document_summaries
            ADD COLUMN document_title TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN document_type TEXT NOT NULL DEFAULT 'unknown'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN coverage_scope_json TEXT NOT NULL DEFAULT '{}'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN positive_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN negative_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN exact_identifiers_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_summaries
            ADD COLUMN routing_notes TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE document_sheet_summaries
            ADD COLUMN header_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE document_sheet_summaries
            ADD COLUMN sampled_identifiers_json TEXT NOT NULL DEFAULT '[]'
            """,
        ),
    ),
    SchemaMigration(
        version=4,
        name="persist_chat_turn_snapshots_and_llm_preferences",
        statements=(
            """
            ALTER TABLE chat_turns
            ADD COLUMN answer_blocks_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN newly_attached_documents_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN attached_documents_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN citations_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN insufficient_evidence INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN follow_up_suggestions_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN warnings_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE chat_turns
            ADD COLUMN timings_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            CREATE TABLE IF NOT EXISTS llm_preferences (
              scope TEXT PRIMARY KEY,
              summary_provider TEXT NOT NULL,
              summary_model TEXT NOT NULL,
              router_provider TEXT NOT NULL,
              router_model TEXT NOT NULL,
              answer_provider TEXT NOT NULL,
              answer_model TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    SchemaMigration(
        version=5,
        name="add_authentication_and_session_ownership",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS user_accounts (
              user_id TEXT PRIMARY KEY,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              last_login_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
              session_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              session_token_hash TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              revoked_at TEXT,
              FOREIGN KEY(user_id) REFERENCES user_accounts(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
              reset_token_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              token_hash TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL,
              used_at TEXT,
              FOREIGN KEY(user_id) REFERENCES user_accounts(user_id)
            )
            """,
            """
            ALTER TABLE chat_sessions
            ADD COLUMN user_id TEXT NOT NULL DEFAULT ''
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
              ON auth_sessions(user_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash
              ON auth_sessions(session_token_hash)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id
              ON password_reset_tokens(user_id)
            """,
        ),
    ),
    SchemaMigration(
        version=6,
        name="add_operational_maintenance_indexes",
        statements=(
            """
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at
              ON auth_sessions(expires_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at
              ON auth_sessions(revoked_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires_at
              ON password_reset_tokens(expires_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_used_at
              ON password_reset_tokens(used_at)
            """,
        ),
    ),
    SchemaMigration(
        version=7,
        name="remove_chat_turn_performance_timings",
        statements=(
            """
            ALTER TABLE chat_turns
            DROP COLUMN timings_json
            """,
        ),
    ),
    SchemaMigration(
        version=8,
        name="soft_delete_excel_files",
        statements=(
            """
            ALTER TABLE excel_files
            ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            """,
            """
            ALTER TABLE excel_files
            ADD COLUMN deleted_at TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_excel_files_status
              ON excel_files(status, updated_at)
            """,
        ),
    ),
    SchemaMigration(
        version=9,
        name="add_excel_file_visibility",
        statements=(
            """
            ALTER TABLE excel_files
            ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_excel_files_visibility
              ON excel_files(status, visibility, updated_at)
            """,
        ),
    ),
    SchemaMigration(
        version=10,
        name="add_row_mapping_raw_order_index",
        statements=(
            """
            CREATE INDEX IF NOT EXISTS idx_mappings_sheet_raw_csv_row
              ON excel_row_mappings(sheet_id, raw_csv_row_number)
            """,
        ),
    ),
    SchemaMigration(
        version=11,
        name="add_upload_tasks_and_shared_chat_cancellations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS excel_upload_tasks (
              task_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              original_filename TEXT NOT NULL,
              staging_path TEXT NOT NULL,
              replace_existing INTEGER NOT NULL,
              status TEXT NOT NULL,
              error_message TEXT,
              result_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              worker_id TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_upload_tasks_status_created
              ON excel_upload_tasks(status, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_request_cancellations (
              request_id TEXT PRIMARY KEY,
              cancelled_at TEXT NOT NULL,
              expires_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_request_cancellations_expires_at
              ON chat_request_cancellations(expires_at)
            """,
        ),
    ),
    SchemaMigration(
        version=12,
        name="add_shared_auth_login_attempts",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS auth_login_attempts (
              email TEXT PRIMARY KEY,
              failures INTEGER NOT NULL,
              first_failure_at TEXT NOT NULL,
              blocked_until TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_auth_login_attempts_blocked_until
              ON auth_login_attempts(blocked_until)
            """,
        ),
    ),
    SchemaMigration(
        version=13,
        name="normalize_storage_artifact_references",
        statements=(
            """
            UPDATE excel_sheets
            SET raw_csv_path = replace(raw_csv_path, char(92), '/')
            WHERE raw_csv_path LIKE '%' || char(92) || '%'
            """,
            """
            UPDATE excel_sheets
            SET raw_csv_path = substr(raw_csv_path, instr(raw_csv_path, '/files/') + 1)
            WHERE raw_csv_path LIKE '%/files/%'
              AND raw_csv_path NOT LIKE 'files/%'
            """,
            """
            UPDATE excel_artifacts
            SET path = replace(path, char(92), '/')
            WHERE path LIKE '%' || char(92) || '%'
            """,
            """
            UPDATE excel_artifacts
            SET path = substr(path, instr(path, '/files/') + 1)
            WHERE path LIKE '%/files/%'
              AND path NOT LIKE 'files/%'
            """,
            """
            UPDATE excel_upload_tasks
            SET staging_path = replace(staging_path, char(92), '/')
            WHERE staging_path LIKE '%' || char(92) || '%'
            """,
            """
            UPDATE excel_upload_tasks
            SET staging_path = substr(staging_path, instr(staging_path, '/upload-tasks/') + 1)
            WHERE staging_path LIKE '%/upload-tasks/%'
              AND staging_path NOT LIKE 'upload-tasks/%'
            """,
        ),
    ),
    SchemaMigration(
        version=14,
        name="add_excel_row_search_fts_index",
        statements=(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS excel_row_search_index
            USING fts5(
              mapping_id UNINDEXED,
              version_id UNINDEXED,
              sheet_id UNINDEXED,
              row_id UNINDEXED,
              original_row_number UNINDEXED,
              raw_csv_row_number UNINDEXED,
              created_at UNINDEXED,
              row_json UNINDEXED,
              searchable_text,
              tokenize='trigram'
            )
            """,
        ),
    ),
)
