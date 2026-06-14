export interface ExcelFile {
  file_id: string
  display_name: string
  active_version_id: string | null
  created_at: string
  updated_at: string
  visible_to_members: boolean
}

export interface ExcelFileVersion {
  version_id: string
  file_id: string
  original_filename: string
  file_hash: string
  status: 'pending' | 'processing' | 'ready' | 'failed' | 'archived'
  error_message: string | null
  created_at: string
  activated_at: string | null
}

export interface ExcelSheet {
  sheet_id: string
  version_id: string
  sheet_index: number
  sheet_code: string
  sheet_name: string
  row_count: number
  column_count: number
  created_at: string
}

export interface ExcelArtifact {
  artifact_id: string
  version_id: string
  artifact_type: 'original' | 'raw_csv' | 'profile' | 'row_mapping'
  path: string
  created_at: string
}

export interface SheetProfile {
  sheet_id: string
  sheet_code: string
  sheet_name: string
  row_count: number
  column_count: number
  candidate_header: string[]
  sample_rows: string[][]
}

export interface WorkbookProfile {
  file_id: string
  version_id: string
  original_filename: string
  file_hash: string
  sheets: SheetProfile[]
}

export interface UploadExcelResponse {
  file: ExcelFile
  version: ExcelFileVersion
  sheets: ExcelSheet[]
  profile: WorkbookProfile
}

export type UploadTaskStatus = 'queued' | 'processing' | 'ready' | 'failed'

export interface CreateUploadTaskResponse {
  task_id: string
  status: UploadTaskStatus
  created_at: string
  updated_at: string
}

export interface UploadTaskResponse {
  task_id: string
  status: UploadTaskStatus
  original_filename: string
  replace_existing: boolean
  error_message: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  result: UploadExcelResponse | null
}

export interface ListExcelFilesResponse {
  files: ExcelFile[]
}

export interface ListExcelVersionsResponse {
  versions: ExcelFileVersion[]
}

export interface ListExcelSheetsResponse {
  sheets: ExcelSheet[]
}

export interface ListExcelArtifactsResponse {
  artifacts: ExcelArtifact[]
}

export interface ActiveExcelFileResponse {
  file: ExcelFile
  version: ExcelFileVersion
}

export interface DeleteExcelFileResponse {
  file_id: string
  display_name: string
  deleted_versions: number
  deleted_sheets: number
  deleted_artifacts: number
  deleted_row_mappings: number
  deleted_summaries: number
  deleted_chat_session_documents: number
}

export interface SheetPreviewResponse {
  sheet: ExcelSheet
  rows: string[][]
  total_rows: number
  offset: number
  limit: number
}

export interface RowMapping {
  row_id: string
  version_id: string
  sheet_id: string
  original_row_number: number
  raw_csv_row_number: number
}

export interface RowLookupResponse {
  sheet: ExcelSheet
  mapping: RowMapping
  row: string[]
}

export interface SheetRow {
  mapping: RowMapping
  row: string[]
}

export interface SheetRowsResponse {
  sheet: ExcelSheet
  rows: SheetRow[]
  total_rows: number
  offset: number
  limit: number
}

export interface SheetSearchMatch {
  sheet: ExcelSheet
  mapping: RowMapping
  row: string[]
  matched_columns: number[]
}

export interface SheetSearchResponse {
  sheet: ExcelSheet
  query: string
  matches: SheetSearchMatch[]
  total_matches: number
  limit: number
}

export interface WorkbookSearchResponse {
  version_id: string
  query: string
  matches: SheetSearchMatch[]
  total_matches: number
  limit: number
}
