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
    SchemaMigration(
        version=15,
        name="add_pdf_knowledge_schema",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_files (
              file_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              parent_id TEXT,
              display_name TEXT NOT NULL,
              original_filename TEXT NOT NULL,
              kind TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              storage_path TEXT,
              status TEXT NOT NULL,
              visibility TEXT NOT NULL,
              processing_status TEXT NOT NULL,
              progress INTEGER NOT NULL,
              status_detail TEXT NOT NULL,
              error_message TEXT,
              page_count INTEGER,
              chunk_count INTEGER,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              deleted_at TEXT,
              FOREIGN KEY(parent_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_files_status_updated
              ON pdf_files(status, updated_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_files_parent
              ON pdf_files(parent_id, display_name)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_upload_tasks (
              task_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              file_id TEXT,
              original_filename TEXT NOT NULL,
              staging_path TEXT NOT NULL,
              status TEXT NOT NULL,
              progress INTEGER NOT NULL,
              detail TEXT NOT NULL,
              error_message TEXT,
              result_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              worker_id TEXT,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_upload_tasks_status_created
              ON pdf_upload_tasks(status, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_document_summaries (
              file_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              content TEXT NOT NULL,
              updated_at TEXT,
              error_message TEXT,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_preview_blocks (
              block_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              page_label TEXT NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              block_index INTEGER NOT NULL,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_preview_blocks_file
              ON pdf_preview_blocks(file_id, block_index)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_schema_items (
              item_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              label TEXT NOT NULL,
              value TEXT NOT NULL,
              item_index INTEGER NOT NULL,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_schema_items_file
              ON pdf_schema_items(file_id, item_index)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_document_tags (
              file_id TEXT NOT NULL,
              tag TEXT NOT NULL,
              tag_index INTEGER NOT NULL,
              PRIMARY KEY(file_id, tag),
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_model_settings (
              setting_id TEXT PRIMARY KEY,
              label TEXT NOT NULL,
              providers_json TEXT NOT NULL,
              models_json TEXT NOT NULL,
              selected_provider TEXT NOT NULL,
              selected_model TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
    SchemaMigration(
        version=16,
        name="add_pdf_document_chunks",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_document_chunks (
              chunk_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              chunk_index INTEGER NOT NULL,
              text TEXT NOT NULL,
              page_label TEXT,
              title TEXT NOT NULL,
              token_count INTEGER NOT NULL,
              content_hash TEXT NOT NULL,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id),
              UNIQUE(file_id, chunk_index)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_document_chunks_file
              ON pdf_document_chunks(file_id, chunk_index)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_document_chunks_hash
              ON pdf_document_chunks(file_id, content_hash)
            """,
        ),
    ),
    SchemaMigration(
        version=17,
        name="add_pdf_upload_task_diagnostics",
        statements=(
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN parser_backend TEXT NOT NULL DEFAULT 'unknown'
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN error_code TEXT
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN last_retry_at TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_upload_tasks_stage_updated
              ON pdf_upload_tasks(stage, updated_at)
            """,
            """
            UPDATE pdf_upload_tasks
            SET stage = CASE
              WHEN status = 'ready' THEN 'ready'
              WHEN status = 'failed' THEN 'failed'
              WHEN status = 'processing' AND progress >= 90 THEN 'indexing'
              WHEN status = 'processing' THEN 'parsing'
              ELSE 'queued'
            END
            WHERE stage = 'queued'
            """,
        ),
    ),
    SchemaMigration(
        version=18,
        name="add_pdf_parse_quality_reports",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_parse_reports (
              file_id TEXT PRIMARY KEY,
              parser_backend TEXT NOT NULL,
              parser_version TEXT,
              quality_status TEXT NOT NULL,
              total_pages INTEGER NOT NULL,
              parsed_pages INTEGER NOT NULL,
              failed_pages INTEGER NOT NULL,
              empty_pages INTEGER NOT NULL,
              text_block_count INTEGER NOT NULL,
              table_block_count INTEGER NOT NULL,
              image_block_count INTEGER NOT NULL,
              chunk_count INTEGER NOT NULL,
              coverage_ratio REAL NOT NULL,
              warning_count INTEGER NOT NULL,
              error_count INTEGER NOT NULL,
              warnings_json TEXT NOT NULL DEFAULT '[]',
              started_at TEXT,
              finished_at TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_parse_pages (
              page_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              page_number INTEGER NOT NULL,
              page_label TEXT NOT NULL,
              status TEXT NOT NULL,
              text_block_count INTEGER NOT NULL,
              table_block_count INTEGER NOT NULL,
              image_block_count INTEGER NOT NULL,
              char_count INTEGER NOT NULL,
              warning_message TEXT,
              error_message TEXT,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id),
              UNIQUE(file_id, page_number)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_parse_pages_file_page
              ON pdf_parse_pages(file_id, page_number)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_parse_pages_file_status
              ON pdf_parse_pages(file_id, status)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_parse_artifacts (
              artifact_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              artifact_type TEXT NOT NULL,
              name TEXT NOT NULL,
              path TEXT,
              size_bytes INTEGER NOT NULL,
              content_hash TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_parse_artifacts_file
              ON pdf_parse_artifacts(file_id, artifact_type)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_files_processing_status
              ON pdf_files(processing_status, updated_at)
            """,
        ),
    ),
    SchemaMigration(
        version=19,
        name="add_pdf_upload_batches",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_upload_batches (
              batch_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              source_name TEXT NOT NULL,
              status TEXT NOT NULL,
              total_files INTEGER NOT NULL,
              accepted_files INTEGER NOT NULL,
              skipped_files INTEGER NOT NULL,
              total_bytes INTEGER NOT NULL,
              progress INTEGER NOT NULL,
              detail TEXT NOT NULL,
              error_message TEXT,
              parser_backend TEXT NOT NULL,
              result_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              completed_at TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_upload_batches_user_updated
              ON pdf_upload_batches(user_id, updated_at)
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN batch_id TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_upload_tasks_batch
              ON pdf_upload_tasks(batch_id, created_at)
            """,
        ),
    ),
    SchemaMigration(
        version=20,
        name="add_chat_workspace_scope",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN workspace TEXT NOT NULL DEFAULT 'excel'
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_workspace_status_updated
              ON chat_sessions(workspace, status, updated_at)
            """,
        ),
    ),
    SchemaMigration(
        version=21,
        name="add_pdf_summary_routing_and_session_documents",
        statements=(
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN document_title TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN document_type TEXT NOT NULL DEFAULT 'pdf_document'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN business_domain TEXT NOT NULL DEFAULT 'pdf knowledge'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN key_topics_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN positive_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN negative_routing_terms_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN exact_identifiers_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN suitable_questions_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN unsuitable_questions_json TEXT NOT NULL DEFAULT '[]'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN routing_notes TEXT NOT NULL DEFAULT ''
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_chat_session_documents (
              session_id TEXT NOT NULL,
              file_id TEXT NOT NULL,
              attached_at TEXT NOT NULL,
              chunk_count INTEGER NOT NULL,
              context_hash TEXT NOT NULL,
              status TEXT NOT NULL,
              PRIMARY KEY(session_id, file_id),
              FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id),
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_chat_session_documents_session
              ON pdf_chat_session_documents(session_id, attached_at)
            """,
        ),
    ),
    SchemaMigration(
        version=22,
        name="add_pdf_summary_tasks",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_summary_tasks (
              task_id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              file_id TEXT NOT NULL,
              status TEXT NOT NULL,
              progress INTEGER NOT NULL,
              detail TEXT NOT NULL,
              error_message TEXT,
              result_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              worker_id TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              last_retry_at TEXT,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_summary_tasks_status_created
              ON pdf_summary_tasks(status, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_summary_tasks_user_updated
              ON pdf_summary_tasks(user_id, updated_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_summary_tasks_file_status
              ON pdf_summary_tasks(file_id, status)
            """,
        ),
    ),
    SchemaMigration(
        version=23,
        name="add_chat_session_context_scope",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN context_file_ids_json TEXT NOT NULL DEFAULT '[]'
            """,
        ),
    ),
    SchemaMigration(
        version=24,
        name="add_chat_turn_request_idempotency_key",
        statements=(
            """
            ALTER TABLE chat_turns
            ADD COLUMN request_id TEXT
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_turns_session_request
              ON chat_turns(session_id, request_id)
              WHERE request_id IS NOT NULL
            """,
        ),
    ),
    SchemaMigration(
        version=25,
        name="add_chat_session_optimistic_revision",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN revision INTEGER NOT NULL DEFAULT 0
            """,
        ),
    ),
    SchemaMigration(
        version=26,
        name="persist_pdf_content_fingerprint",
        statements=(
            """
            ALTER TABLE pdf_files
            ADD COLUMN content_fingerprint TEXT NOT NULL DEFAULT ''
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_files_content_fingerprint
              ON pdf_files(content_fingerprint)
              WHERE content_fingerprint <> ''
            """,
        ),
    ),
    SchemaMigration(
        version=27,
        name="add_excel_chat_conversation_revision",
        statements=(
            """
            ALTER TABLE chat_sessions
            ADD COLUMN conversation_revision INTEGER NOT NULL DEFAULT 0
            """,
        ),
    ),
    SchemaMigration(
        version=28,
        name="add_excel_chat_request_executions",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS chat_request_executions (
              workspace TEXT NOT NULL,
              session_id TEXT NOT NULL,
              request_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              request_fingerprint TEXT NOT NULL,
              status TEXT NOT NULL,
              lease_expires_at TEXT NOT NULL,
              turn_id TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(workspace, session_id, request_id),
              FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id),
              FOREIGN KEY(turn_id) REFERENCES chat_turns(turn_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_request_executions_lease
              ON chat_request_executions(status, lease_expires_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_chat_request_executions_turn
              ON chat_request_executions(turn_id)
              WHERE turn_id IS NOT NULL
            """,
        ),
    ),
    SchemaMigration(
        version=29,
        name="harden_pdf_summary_content_and_task_consistency",
        statements=(
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN source_fingerprint TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN source_updated_at TEXT
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN provider TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN model TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN prompt_version TEXT NOT NULL DEFAULT 'pdf-summary-v1'
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN generation_task_id TEXT
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN generated_by_user_id TEXT
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN revision INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE pdf_document_summaries
            ADD COLUMN created_at TEXT
            """,
            """
            UPDATE pdf_document_summaries
            SET source_fingerprint = COALESCE(
                  (SELECT content_fingerprint
                   FROM pdf_files
                   WHERE pdf_files.file_id = pdf_document_summaries.file_id),
                  ''
                ),
                source_updated_at = COALESCE(
                  (SELECT updated_at
                   FROM pdf_files
                   WHERE pdf_files.file_id = pdf_document_summaries.file_id),
                  updated_at
                ),
                created_at = COALESCE(created_at, updated_at)
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN source_fingerprint TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN claim_token TEXT
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN claimed_at TEXT
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1
            """,
            """
            ALTER TABLE pdf_summary_tasks
            ADD COLUMN parent_task_id TEXT
            """,
            """
            UPDATE pdf_summary_tasks
            SET source_fingerprint = COALESCE(
              (SELECT content_fingerprint
               FROM pdf_files
               WHERE pdf_files.file_id = pdf_summary_tasks.file_id),
              ''
            )
            """,
            """
            UPDATE pdf_summary_tasks
            SET status = 'failed',
                progress = 100,
                detail = 'Superseded duplicate task during schema upgrade.',
                error_message = 'A newer consistency rule replaced this duplicate task.',
                finished_at = COALESCE(finished_at, updated_at),
                state_revision = state_revision + 1
            WHERE status IN ('queued', 'running')
              AND task_id NOT IN (
                SELECT MIN(task_id)
                FROM pdf_summary_tasks
                WHERE status IN ('queued', 'running')
                GROUP BY file_id
              )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_summary_tasks_one_active_file
              ON pdf_summary_tasks(file_id)
              WHERE status IN ('queued', 'running')
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_summary_source_fingerprint
              ON pdf_document_summaries(file_id, source_fingerprint)
            """,
        ),
    ),
    SchemaMigration(
        version=30,
        name="add_pdf_file_cleanup_outbox",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_file_cleanup_jobs (
              job_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              relative_path TEXT NOT NULL,
              status TEXT NOT NULL,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              error_message TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              completed_at TEXT
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_cleanup_job_path_active
              ON pdf_file_cleanup_jobs(relative_path)
              WHERE status IN ('pending', 'failed')
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_cleanup_jobs_status_updated
              ON pdf_file_cleanup_jobs(status, updated_at)
            """,
        ),
    ),
    SchemaMigration(
        version=31,
        name="enforce_one_active_pdf_upload_task_per_file",
        statements=(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_upload_tasks_one_active_file
              ON pdf_upload_tasks(file_id)
              WHERE file_id IS NOT NULL AND status IN ('queued', 'processing')
            """,
        ),
    ),
    SchemaMigration(
        version=32,
        name="enforce_unique_active_pdf_sibling_names",
        statements=(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_files_unique_active_sibling_name
              ON pdf_files(user_id, COALESCE(parent_id, ''), display_name)
              WHERE status = 'active'
            """,
        ),
    ),
    SchemaMigration(
        version=33,
        name="add_upload_task_claim_fencing",
        statements=(
            """
            ALTER TABLE excel_upload_tasks ADD COLUMN claim_token TEXT
            """,
            """
            ALTER TABLE excel_upload_tasks ADD COLUMN lease_expires_at TEXT
            """,
            """
            ALTER TABLE excel_upload_tasks ADD COLUMN heartbeat_at TEXT
            """,
            """
            ALTER TABLE excel_upload_tasks
              ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 0
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_excel_upload_tasks_active_lease
              ON excel_upload_tasks(status, lease_expires_at)
            """,
            """
            ALTER TABLE pdf_upload_tasks ADD COLUMN claim_token TEXT
            """,
            """
            ALTER TABLE pdf_upload_tasks ADD COLUMN lease_expires_at TEXT
            """,
            """
            ALTER TABLE pdf_upload_tasks ADD COLUMN heartbeat_at TEXT
            """,
            """
            ALTER TABLE pdf_upload_tasks
              ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 0
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_upload_tasks_active_lease
              ON pdf_upload_tasks(status, lease_expires_at)
            """,
        ),
    ),
    SchemaMigration(
        version=34,
        name="add_pdf_cleanup_job_claim_fencing",
        statements=(
            """
            ALTER TABLE pdf_file_cleanup_jobs ADD COLUMN worker_id TEXT
            """,
            """
            ALTER TABLE pdf_file_cleanup_jobs ADD COLUMN claim_token TEXT
            """,
            """
            ALTER TABLE pdf_file_cleanup_jobs ADD COLUMN lease_expires_at TEXT
            """,
            """
            ALTER TABLE pdf_file_cleanup_jobs ADD COLUMN heartbeat_at TEXT
            """,
            """
            ALTER TABLE pdf_file_cleanup_jobs
              ADD COLUMN state_revision INTEGER NOT NULL DEFAULT 0
            """,
            """
            DROP INDEX IF EXISTS idx_pdf_cleanup_job_path_active
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_cleanup_job_path_active
              ON pdf_file_cleanup_jobs(relative_path)
              WHERE status IN ('pending', 'processing', 'failed')
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_cleanup_jobs_active_lease
              ON pdf_file_cleanup_jobs(status, lease_expires_at)
            """,
        ),
    ),
    SchemaMigration(
        version=35,
        name="reconcile_historical_deleted_pdf_content",
        statements=(
            """
            INSERT OR IGNORE INTO pdf_file_cleanup_jobs
              (
                job_id, file_id, relative_path, status, attempt_count,
                error_message, created_at, updated_at, completed_at
              )
            SELECT
              'pdfcleanup_backfill_' || file_id,
              file_id,
              'pdf-knowledge/files/' || file_id,
              'pending',
              0,
              NULL,
              COALESCE(deleted_at, updated_at, created_at),
              COALESCE(deleted_at, updated_at, created_at),
              NULL
            FROM pdf_files
            WHERE status = 'deleted' AND storage_path IS NOT NULL
            """,
            """
            DELETE FROM pdf_chat_session_documents
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_document_chunks
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_preview_blocks
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_schema_items
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_document_tags
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_parse_pages
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_parse_artifacts
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_parse_reports
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
            """
            DELETE FROM pdf_document_summaries
            WHERE file_id IN (SELECT file_id FROM pdf_files WHERE status = 'deleted')
            """,
        ),
    ),
    SchemaMigration(
        version=36,
        name="add_pdf_vector_index_state_and_tasks",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS pdf_vector_indexes (
              file_id TEXT PRIMARY KEY,
              source_fingerprint TEXT NOT NULL,
              embedding_revision TEXT NOT NULL,
              embedding_dimension INTEGER NOT NULL CHECK(embedding_dimension > 0),
              status TEXT NOT NULL
                CHECK(status IN ('pending', 'running', 'ready', 'failed')),
              expected_chunk_count INTEGER NOT NULL
                CHECK(expected_chunk_count >= 0),
              indexed_chunk_count INTEGER NOT NULL DEFAULT 0
                CHECK(indexed_chunk_count >= 0),
              last_error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              ready_at TEXT,
              state_revision INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY(file_id) REFERENCES pdf_files(file_id),
              CHECK(status != 'ready' OR indexed_chunk_count = expected_chunk_count)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_vector_indexes_status_updated
              ON pdf_vector_indexes(status, updated_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS pdf_vector_index_tasks (
              task_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              action TEXT NOT NULL CHECK(action IN ('index', 'delete')),
              source_fingerprint TEXT NOT NULL,
              embedding_revision TEXT NOT NULL,
              status TEXT NOT NULL CHECK(
                status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')
              ),
              attempt_count INTEGER NOT NULL DEFAULT 0
                CHECK(attempt_count >= 0),
              error_message TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              worker_id TEXT,
              claim_token TEXT,
              lease_expires_at TEXT,
              heartbeat_at TEXT,
              state_revision INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_vector_tasks_one_active_file
              ON pdf_vector_index_tasks(file_id)
              WHERE status IN ('pending', 'running', 'failed')
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_vector_tasks_claim_order
              ON pdf_vector_index_tasks(status, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_vector_tasks_active_lease
              ON pdf_vector_index_tasks(status, lease_expires_at)
            """,
        ),
    ),
    SchemaMigration(
        version=37,
        name="add_pdf_vector_task_retry_schedule",
        statements=(
            """
            ALTER TABLE pdf_vector_index_tasks ADD COLUMN next_attempt_at TEXT
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_vector_tasks_retry_schedule
              ON pdf_vector_index_tasks(status, next_attempt_at, created_at)
            """,
        ),
    ),
    SchemaMigration(
        version=38,
        name="harden_pdf_vector_task_lifecycle",
        statements=(
            """
            DROP INDEX IF EXISTS idx_pdf_vector_tasks_one_active_file
            """,
            """
            DROP INDEX IF EXISTS idx_pdf_vector_tasks_claim_order
            """,
            """
            DROP INDEX IF EXISTS idx_pdf_vector_tasks_active_lease
            """,
            """
            DROP INDEX IF EXISTS idx_pdf_vector_tasks_retry_schedule
            """,
            """
            ALTER TABLE pdf_vector_index_tasks
              RENAME TO pdf_vector_index_tasks_legacy
            """,
            """
            CREATE TABLE pdf_vector_index_tasks (
              task_id TEXT PRIMARY KEY,
              file_id TEXT NOT NULL,
              action TEXT NOT NULL CHECK(action IN ('index', 'delete')),
              source_fingerprint TEXT NOT NULL,
              embedding_revision TEXT NOT NULL,
              status TEXT NOT NULL CHECK(
                status IN (
                  'pending', 'running', 'retry_wait', 'succeeded',
                  'dead_letter', 'cancelled'
                )
              ),
              attempt_count INTEGER NOT NULL DEFAULT 0
                CHECK(attempt_count >= 0),
              error_message TEXT,
              error_code TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              worker_id TEXT,
              claim_token TEXT,
              lease_expires_at TEXT,
              heartbeat_at TEXT,
              next_attempt_at TEXT,
              parent_task_id TEXT,
              state_revision INTEGER NOT NULL DEFAULT 0,
              CHECK(
                (status = 'pending'
                  AND started_at IS NULL
                  AND finished_at IS NULL
                  AND worker_id IS NULL
                  AND claim_token IS NULL
                  AND lease_expires_at IS NULL
                  AND heartbeat_at IS NULL
                  AND next_attempt_at IS NULL)
                OR
                (status = 'running'
                  AND started_at IS NOT NULL
                  AND finished_at IS NULL
                  AND worker_id IS NOT NULL
                  AND claim_token IS NOT NULL
                  AND lease_expires_at IS NOT NULL
                  AND heartbeat_at IS NOT NULL
                  AND next_attempt_at IS NULL)
                OR
                (status = 'retry_wait'
                  AND started_at IS NOT NULL
                  AND finished_at IS NULL
                  AND worker_id IS NULL
                  AND claim_token IS NULL
                  AND lease_expires_at IS NULL
                  AND heartbeat_at IS NULL
                  AND next_attempt_at IS NOT NULL)
                OR
                (status IN ('succeeded', 'dead_letter', 'cancelled')
                  AND finished_at IS NOT NULL
                  AND worker_id IS NULL
                  AND claim_token IS NULL
                  AND lease_expires_at IS NULL
                  AND heartbeat_at IS NULL
                  AND next_attempt_at IS NULL)
              )
            )
            """,
            """
            INSERT INTO pdf_vector_index_tasks (
              task_id, file_id, action, source_fingerprint, embedding_revision,
              status, attempt_count, error_message, error_code, created_at,
              updated_at, started_at, finished_at, worker_id, claim_token,
              lease_expires_at, heartbeat_at, next_attempt_at, parent_task_id,
              state_revision
            )
            SELECT
              task_id,
              file_id,
              action,
              source_fingerprint,
              embedding_revision,
              CASE
                WHEN status = 'failed' AND attempt_count < 10 THEN 'retry_wait'
                WHEN status = 'failed' THEN 'dead_letter'
                ELSE status
              END,
              attempt_count,
              error_message,
              CASE
                WHEN status = 'failed' AND attempt_count < 10
                  THEN 'LEGACY_RETRYABLE_FAILURE'
                WHEN status = 'failed' THEN 'LEGACY_RETRY_EXHAUSTED'
                ELSE NULL
              END,
              created_at,
              updated_at,
              CASE WHEN status = 'pending' THEN NULL ELSE started_at END,
              CASE
                WHEN status IN ('succeeded', 'cancelled')
                  OR (status = 'failed' AND attempt_count >= 10)
                  THEN COALESCE(finished_at, updated_at)
                ELSE NULL
              END,
              CASE WHEN status = 'running' THEN worker_id ELSE NULL END,
              CASE WHEN status = 'running' THEN claim_token ELSE NULL END,
              CASE WHEN status = 'running' THEN lease_expires_at ELSE NULL END,
              CASE WHEN status = 'running' THEN heartbeat_at ELSE NULL END,
              CASE
                WHEN status = 'failed' AND attempt_count < 10
                  THEN COALESCE(next_attempt_at, updated_at)
                ELSE NULL
              END,
              NULL,
              state_revision
            FROM pdf_vector_index_tasks_legacy
            """,
            """
            DROP TABLE pdf_vector_index_tasks_legacy
            """,
            """
            CREATE UNIQUE INDEX idx_pdf_vector_tasks_one_active_file
              ON pdf_vector_index_tasks(file_id)
              WHERE status IN ('pending', 'running', 'retry_wait')
            """,
            """
            CREATE INDEX idx_pdf_vector_tasks_claim_order
              ON pdf_vector_index_tasks(status, created_at)
            """,
            """
            CREATE INDEX idx_pdf_vector_tasks_active_lease
              ON pdf_vector_index_tasks(status, lease_expires_at)
            """,
            """
            CREATE INDEX idx_pdf_vector_tasks_retry_schedule
              ON pdf_vector_index_tasks(status, next_attempt_at, created_at)
            """,
            """
            CREATE INDEX idx_pdf_vector_tasks_parent
              ON pdf_vector_index_tasks(parent_task_id)
            """,
        ),
    ),
    SchemaMigration(
        version=39,
        name="add_pdf_vector_projection_generations",
        statements=(
            """
            ALTER TABLE pdf_vector_indexes
              ADD COLUMN generation INTEGER NOT NULL DEFAULT 1
              CHECK(generation > 0)
            """,
            """
            ALTER TABLE pdf_vector_index_tasks
              ADD COLUMN generation INTEGER NOT NULL DEFAULT 1
              CHECK(generation > 0)
            """,
            """
            CREATE TABLE pdf_vector_projection_epochs (
              file_id TEXT PRIMARY KEY,
              current_generation INTEGER NOT NULL CHECK(current_generation > 0),
              tombstoned INTEGER NOT NULL DEFAULT 0 CHECK(tombstoned IN (0, 1)),
              updated_at TEXT NOT NULL
            )
            """,
            """
            INSERT INTO pdf_vector_projection_epochs (
              file_id, current_generation, tombstoned, updated_at
            )
            SELECT
              source.file_id,
              1,
              CASE
                WHEN EXISTS (
                  SELECT 1 FROM pdf_files AS file
                  WHERE file.file_id = source.file_id AND file.status = 'deleted'
                ) THEN 1
                ELSE 0
              END,
              MAX(source.updated_at)
            FROM (
              SELECT file_id, updated_at FROM pdf_vector_indexes
              UNION ALL
              SELECT file_id, updated_at FROM pdf_vector_index_tasks
            ) AS source
            GROUP BY source.file_id
            """,
            """
            CREATE INDEX idx_pdf_vector_epochs_tombstone
              ON pdf_vector_projection_epochs(tombstoned, updated_at)
            """,
        ),
    ),
)
