import { chatRequestOptions, defaultRequestOptions } from './config'
import { requestEmpty, requestJson } from './errors'
import type {
  PdfAnswerBlock,
  PdfAnswerCitation,
  PdfChunkSearchMatch,
  PdfChunkSearchResult,
  PdfAttachedDocument,
  PdfChatAnswer,
  PdfChatSession,
  PdfChatTurn,
  PdfDocumentChunk,
  PdfDocumentDetail,
  PdfDocumentPreviewBlock,
  PdfDocumentSchemaItem,
  PdfDocumentSummary,
  PdfManagedFile,
  PdfManagedFileKind,
  PdfManagedFileStatus,
  PdfModelSetting,
  PdfParseArtifact,
  PdfParsePage,
  PdfParsePageStatus,
  PdfParseQualityStatus,
  PdfParseReport,
  PdfParserProfile,
  PdfParserProfiles,
  PdfParserStatus,
  PdfSelectedDocument,
  PdfSummaryTask,
  PdfSummaryTaskStatus,
  PdfUploadBatch,
  PdfUploadCreationResult,
  PdfUploadSkippedFile,
  PdfUploadTask,
  PdfUploadTaskStatus,
} from '../features/pdf-knowledge/types'

interface PdfFileResponse {
  file_id: string
  parent_id: string | null
  kind: PdfManagedFileKind
  display_name: string
  original_filename: string
  size_bytes: number
  status: string
  processing_status: PdfManagedFileStatus
  progress: number
  status_detail: string
  error_message: string | null
  page_count: number | null
  chunk_count: number | null
  quality_status?: PdfParseQualityStatus | null
  coverage_ratio?: number | null
  warning_count?: number | null
  failed_page_count?: number | null
  parser_backend?: string | null
  created_at: string
  updated_at: string
  visible_to_members: boolean
}

interface ListPdfFilesResponse {
  files: PdfFileResponse[]
}

interface PdfParserStatusResponse {
  backend: string
  available: boolean
  command: string | null
  version: string | null
  detail: string
}

interface PdfParserProfileResponse {
  id: string
  label: string
  kind: string
  backend: string
  available: boolean
  command: string | null
  version: string | null
  detail: string
  description: string
  is_default: boolean
  is_selected: boolean
}

interface ListPdfParserProfilesResponse {
  selected_profile_id: string
  profiles: PdfParserProfileResponse[]
}

interface PdfUploadTaskResponse {
  task_id: string
  file_id: string | null
  batch_id: string | null
  original_filename: string
  status: PdfUploadTaskStatus
  stage: PdfUploadTask['stage']
  progress: number
  detail: string
  error_message: string | null
  error_code: string | null
  parser_backend: string
  retry_count: number
  result: Record<string, unknown>
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  last_retry_at: string | null
}

interface PdfUploadBatchResponse {
  batch_id: string
  source_name: string
  status: PdfUploadBatch['status']
  total_files: number
  accepted_files: number
  skipped_files: number
  total_bytes: number
  progress: number
  detail: string
  error_message: string | null
  parser_backend: string
  result: Record<string, unknown>
  created_at: string
  updated_at: string
  completed_at: string | null
}

interface CreatePdfUploadTasksResponse {
  batch: PdfUploadBatchResponse | null
  tasks: PdfUploadTaskResponse[]
}

interface ListPdfUploadTasksResponse {
  tasks: PdfUploadTaskResponse[]
}

interface ListPdfUploadBatchesResponse {
  batches: PdfUploadBatchResponse[]
}

interface PdfUploadBatchDetailResponse {
  batch: PdfUploadBatchResponse
  tasks: PdfUploadTaskResponse[]
}

interface PdfSummaryTaskResponse {
  task_id: string
  file_id: string
  status: string
  progress: number
  detail: string
  error_message: string | null
  retry_count: number
  result: Record<string, unknown>
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  last_retry_at: string | null
}

interface CreatePdfSummaryTasksResponse {
  tasks: PdfSummaryTaskResponse[]
}

interface ListPdfSummaryTasksResponse {
  tasks: PdfSummaryTaskResponse[]
}

interface PdfDocumentSummaryResponse {
  file_id: string
  status: PdfDocumentSummary['status']
  content: string
  updated_at: string | null
  error_message: string | null
  document_title?: string
  document_type?: string
  business_domain?: string
  key_topics?: string[]
  positive_routing_terms?: string[]
  negative_routing_terms?: string[]
  exact_identifiers?: string[]
  suitable_questions?: string[]
  unsuitable_questions?: string[]
  routing_notes?: string
}

interface PdfPreviewBlockResponse {
  block_id: string
  page_label: string
  title: string
  content: string
}

interface PdfSchemaItemResponse {
  item_id: string
  label: string
  value: string
}

interface PdfParsePageResponse {
  page_id: string
  page_number: number
  page_label: string
  status: PdfParsePageStatus
  text_block_count: number
  table_block_count: number
  image_block_count: number
  char_count: number
  warning_message: string | null
  error_message: string | null
}

interface PdfParseArtifactResponse {
  artifact_id: string
  artifact_type: string
  name: string
  path: string | null
  size_bytes: number
  content_hash: string | null
  created_at: string
}

interface PdfParseReportResponse {
  file_id: string
  parser_backend: string
  parser_version: string | null
  quality_status: PdfParseQualityStatus
  total_pages: number
  parsed_pages: number
  failed_pages: number
  empty_pages: number
  text_block_count: number
  table_block_count: number
  image_block_count: number
  chunk_count: number
  coverage_ratio: number
  warning_count: number
  error_count: number
  warnings: string[]
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
  pages: PdfParsePageResponse[]
  artifacts: PdfParseArtifactResponse[]
}

interface PdfDocumentDetailResponse {
  file_id: string
  summary: PdfDocumentSummaryResponse
  preview_blocks: PdfPreviewBlockResponse[]
  schema: PdfSchemaItemResponse[]
  tags: string[]
  parse_report: PdfParseReportResponse | null
}

interface PdfDocumentChunkResponse {
  chunk_id: string
  chunk_index: number
  text: string
  page_label: string | null
  title: string
  token_count: number
  content_hash: string
  metadata: Record<string, string>
}

interface ListPdfDocumentChunksResponse {
  chunks: PdfDocumentChunkResponse[]
}

interface PdfChunkSearchMatchResponse {
  file: PdfFileResponse
  chunk: PdfDocumentChunkResponse
  score: number
  excerpt: string
  matched_terms: string[]
}

interface SearchPdfChunksResponse {
  query: string
  matches: PdfChunkSearchMatchResponse[]
  total_matches: number
  limit: number
}

interface PdfChatAnswerBlockResponse {
  text: string
  citation_ids: string[]
  reasoning: string
}

interface PdfCitationResponse {
  citation_id: string
  evidence_id: string
  file_id: string
  file_name: string
  chunk_id: string
  chunk_index: number
  page_label: string | null
  title: string
  quote: string
}

interface PdfSelectedDocumentResponse {
  file_id: string
  version_id: string
  reason: string
  confidence: number | null
}

interface PdfAttachedDocumentResponse {
  file_id: string
  attached_at: string
  chunk_count: number
  context_hash: string
  status: string
}

interface PdfChatAnswerResponse {
  session_id: string | null
  question: string
  answer_blocks: PdfChatAnswerBlockResponse[]
  citations: PdfCitationResponse[]
  retrieval_matches: PdfChunkSearchMatchResponse[]
  selected_documents?: PdfSelectedDocumentResponse[]
  newly_attached_documents?: PdfSelectedDocumentResponse[]
  attached_documents?: PdfAttachedDocumentResponse[]
  insufficient_evidence: boolean
  follow_up_suggestions: string[]
  warnings: string[]
  created_at: string
}

interface PdfChatSessionResponse {
  session_id: string
  user_id: string
  created_at: string
  updated_at: string
  title: string
  pinned_at: string | null
  status: string
}

interface PdfChatSessionListResponse {
  sessions: PdfChatSessionResponse[]
}

interface PdfChatTurnResponse {
  turn_id: string
  session_id: string
  question: string
  answer: PdfChatAnswerResponse
  created_at: string
}

interface PdfChatTurnListResponse {
  turns: PdfChatTurnResponse[]
}

interface GeneratePdfSummaryResponse {
  summary: PdfDocumentSummaryResponse
}

interface PdfModelSettingResponse {
  id: string
  label: string
  providers: string[]
  models: string[]
  provider_models?: Record<string, string[]>
  selected_provider: string
  selected_model: string
}

interface ListPdfModelSettingsResponse {
  settings: PdfModelSettingResponse[]
}

export async function listPdfKnowledgeFiles(): Promise<PdfManagedFile[]> {
  const response = await requestJson<ListPdfFilesResponse>(
    '/api/pdf/files',
    {},
    defaultRequestOptions,
  )
  return response.files.map(toManagedFile)
}

export async function renamePdfFile(fileId: string, displayName: string): Promise<PdfManagedFile> {
  const response = await requestJson<PdfFileResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    },
    defaultRequestOptions,
  )
  return toManagedFile(response)
}

export async function setPdfFileVisibility(
  fileId: string,
  visibleToMembers: boolean,
): Promise<PdfManagedFile> {
  const response = await requestJson<PdfFileResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/visibility`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ visible_to_members: visibleToMembers }),
    },
    defaultRequestOptions,
  )
  return toManagedFile(response)
}

export async function deletePdfFile(fileId: string, confirmDelete = false): Promise<void> {
  await requestJson<unknown>(
    `/api/pdf/files/${encodeURIComponent(fileId)}?confirm_delete=${String(confirmDelete)}`,
    { method: 'DELETE' },
    defaultRequestOptions,
  )
}

export async function getPdfParserStatus(): Promise<PdfParserStatus> {
  const response = await requestJson<PdfParserStatusResponse>(
    '/api/pdf/parser/status',
    {},
    defaultRequestOptions,
  )
  return toParserStatus(response)
}

export async function listPdfParserProfiles(): Promise<PdfParserProfiles> {
  const response = await requestJson<ListPdfParserProfilesResponse>(
    '/api/pdf/parser/profiles',
    {},
    defaultRequestOptions,
  )
  return toParserProfiles(response)
}

export async function updatePdfParserProfile(profileId: string): Promise<PdfParserProfiles> {
  const response = await requestJson<ListPdfParserProfilesResponse>(
    '/api/pdf/parser/profiles',
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selected_profile_id: profileId }),
    },
    defaultRequestOptions,
  )
  return toParserProfiles(response)
}

export async function listPdfUploadTasks(): Promise<PdfUploadTask[]> {
  const response = await requestJson<ListPdfUploadTasksResponse>(
    '/api/pdf/files/upload-tasks',
    {},
    defaultRequestOptions,
  )
  return response.tasks.map(toUploadTask)
}

export async function getPdfUploadTask(taskId: string): Promise<PdfUploadTask> {
  const response = await requestJson<PdfUploadTaskResponse>(
    `/api/pdf/files/upload-tasks/${encodeURIComponent(taskId)}`,
    {},
    defaultRequestOptions,
  )
  return toUploadTask(response)
}

export async function listPdfUploadBatches(): Promise<PdfUploadBatch[]> {
  const response = await requestJson<ListPdfUploadBatchesResponse>(
    '/api/pdf/files/upload-batches',
    {},
    defaultRequestOptions,
  )
  return response.batches.map(toUploadBatch)
}

export async function getPdfUploadBatch(batchId: string): Promise<PdfUploadCreationResult> {
  const response = await requestJson<PdfUploadBatchDetailResponse>(
    `/api/pdf/files/upload-batches/${encodeURIComponent(batchId)}`,
    {},
    defaultRequestOptions,
  )
  return {
    batch: toUploadBatch(response.batch),
    tasks: response.tasks.map(toUploadTask),
  }
}

export async function createPdfUploadTask(
  files: File[],
  parentId?: string,
): Promise<PdfUploadCreationResult> {
  const body = new FormData()
  if (parentId?.trim()) {
    body.append('parent_id', parentId.trim())
  }
  files.forEach((file) => {
    body.append('files', file, uploadPathForFile(file))
  })
  const response = await requestJson<CreatePdfUploadTasksResponse>(
    '/api/pdf/files/upload-tasks',
    {
      method: 'POST',
      body,
    },
    {
      ...defaultRequestOptions,
      timeoutMs: Math.max(defaultRequestOptions.timeoutMs ?? 30000, 120000),
      timeoutMessage: 'PDF upload is still being parsed. Please try again shortly.',
    },
  )
  return {
    batch: response.batch ? toUploadBatch(response.batch) : undefined,
    tasks: response.tasks.map(toUploadTask),
  }
}

export async function cancelPdfUploadTask(taskId: string): Promise<PdfUploadTask> {
  const response = await requestJson<PdfUploadTaskResponse>(
    `/api/pdf/files/upload-tasks/${encodeURIComponent(taskId)}/cancel`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toUploadTask(response)
}

export async function retryPdfUploadTask(taskId: string): Promise<PdfUploadTask> {
  const response = await requestJson<PdfUploadTaskResponse>(
    `/api/pdf/files/upload-tasks/${encodeURIComponent(taskId)}/retry`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toUploadTask(response)
}

export async function listPdfSummaryTasks(): Promise<PdfSummaryTask[]> {
  const response = await requestJson<ListPdfSummaryTasksResponse>(
    '/api/pdf/summary-tasks',
    {},
    defaultRequestOptions,
  )
  return response.tasks.map(toSummaryTask)
}

export async function getPdfSummaryTask(taskId: string): Promise<PdfSummaryTask> {
  const response = await requestJson<PdfSummaryTaskResponse>(
    `/api/pdf/summary-tasks/${encodeURIComponent(taskId)}`,
    {},
    defaultRequestOptions,
  )
  return toSummaryTask(response)
}

export async function createPdfSummaryTasks(options: {
  fileIds?: string[]
  parentId?: string
  includeDescendants?: boolean
  force?: boolean
} = {}): Promise<PdfSummaryTask[]> {
  const response = await requestJson<CreatePdfSummaryTasksResponse>(
    '/api/pdf/summary-tasks',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_ids: options.fileIds ?? [],
        parent_id: options.parentId ?? null,
        include_descendants: options.includeDescendants ?? true,
        force: options.force ?? false,
      }),
    },
    defaultRequestOptions,
  )
  return response.tasks.map(toSummaryTask)
}

export async function cancelPdfSummaryTask(taskId: string): Promise<PdfSummaryTask> {
  const response = await requestJson<PdfSummaryTaskResponse>(
    `/api/pdf/summary-tasks/${encodeURIComponent(taskId)}/cancel`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toSummaryTask(response)
}

export async function retryPdfSummaryTask(taskId: string): Promise<PdfSummaryTask> {
  const response = await requestJson<PdfSummaryTaskResponse>(
    `/api/pdf/summary-tasks/${encodeURIComponent(taskId)}/retry`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toSummaryTask(response)
}

export async function cancelPdfUploadBatch(batchId: string): Promise<PdfUploadCreationResult> {
  const response = await requestJson<PdfUploadBatchDetailResponse>(
    `/api/pdf/files/upload-batches/${encodeURIComponent(batchId)}/cancel`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return {
    batch: toUploadBatch(response.batch),
    tasks: response.tasks.map(toUploadTask),
  }
}

export async function retryPdfUploadBatch(batchId: string): Promise<PdfUploadCreationResult> {
  const response = await requestJson<CreatePdfUploadTasksResponse>(
    `/api/pdf/files/upload-batches/${encodeURIComponent(batchId)}/retry`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return {
    batch: response.batch ? toUploadBatch(response.batch) : undefined,
    tasks: response.tasks.map(toUploadTask),
  }
}

export async function getPdfDocumentDetail(fileId: string): Promise<PdfDocumentDetail> {
  const response = await requestJson<PdfDocumentDetailResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/detail`,
    {},
    defaultRequestOptions,
  )
  return toDocumentDetail(response)
}

export async function reparsePdfDocument(fileId: string): Promise<PdfUploadTask> {
  const response = await requestJson<PdfUploadTaskResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/reparse`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toUploadTask(response)
}

export async function listPdfDocumentChunks(fileId: string): Promise<PdfDocumentChunk[]> {
  const response = await requestJson<ListPdfDocumentChunksResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/chunks`,
    {},
    defaultRequestOptions,
  )
  return response.chunks.map(toDocumentChunk)
}

export async function searchPdfDocumentChunks(options: {
  query: string
  fileIds?: string[]
  limit?: number
}): Promise<PdfChunkSearchResult> {
  const response = await requestJson<SearchPdfChunksResponse>(
    '/api/pdf/retrieval/search',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: options.query,
        file_ids: options.fileIds ?? [],
        limit: options.limit ?? 12,
      }),
    },
    defaultRequestOptions,
  )
  return {
    query: response.query,
    matches: response.matches.map(toChunkSearchMatch),
    totalMatches: response.total_matches,
    limit: response.limit,
  }
}

export async function answerPdfQuestion(options: {
  question: string
  sessionId?: string
  fileIds?: string[]
  retrievalLimit?: number
  enableDeepThinking?: boolean
  signal?: AbortSignal
}): Promise<PdfChatAnswer> {
  const path = options.sessionId
    ? `/api/pdf/chat/sessions/${encodeURIComponent(options.sessionId)}/messages`
    : '/api/pdf/chat'
  const response = await requestJson<PdfChatAnswerResponse>(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: options.question,
        file_ids: options.fileIds ?? [],
        retrieval_limit: options.retrievalLimit ?? 8,
        enable_deep_thinking: options.enableDeepThinking ?? false,
      }),
    },
    {
      ...chatRequestOptions,
      abortMessage: 'PDF chat request cancelled.',
      signal: options.signal,
    },
  )
  return toPdfChatAnswer(response)
}

export async function createPdfChatSession(signal?: AbortSignal): Promise<PdfChatSession> {
  const response = await requestJson<PdfChatSessionResponse>(
    '/api/pdf/chat/sessions',
    { method: 'POST' },
    {
      ...defaultRequestOptions,
      abortMessage: 'PDF chat session request cancelled.',
      signal,
    },
  )
  return toPdfChatSession(response)
}

export async function listPdfChatSessions(signal?: AbortSignal): Promise<PdfChatSession[]> {
  const response = await requestJson<PdfChatSessionListResponse>(
    '/api/pdf/chat/sessions',
    {},
    {
      ...defaultRequestOptions,
      abortMessage: 'PDF chat session request cancelled.',
      signal,
    },
  )
  return response.sessions.map(toPdfChatSession)
}

export async function listPdfChatSessionTurns(
  sessionId: string,
  signal?: AbortSignal,
): Promise<PdfChatTurn[]> {
  const response = await requestJson<PdfChatTurnListResponse>(
    `/api/pdf/chat/sessions/${encodeURIComponent(sessionId)}/turns`,
    {},
    {
      ...defaultRequestOptions,
      abortMessage: 'PDF chat history request cancelled.',
      signal,
    },
  )
  return response.turns.map(toPdfChatTurn)
}

export async function renamePdfChatSession(
  sessionId: string,
  title: string,
): Promise<PdfChatSession> {
  const response = await requestJson<PdfChatSessionResponse>(
    `/api/pdf/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    },
    defaultRequestOptions,
  )
  return toPdfChatSession(response)
}

export async function setPdfChatSessionPinned(
  sessionId: string,
  pinned: boolean,
): Promise<PdfChatSession> {
  const response = await requestJson<PdfChatSessionResponse>(
    `/api/pdf/chat/sessions/${encodeURIComponent(sessionId)}/pin`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned }),
    },
    defaultRequestOptions,
  )
  return toPdfChatSession(response)
}

export async function deletePdfChatSession(sessionId: string): Promise<void> {
  await requestEmpty(
    `/api/pdf/chat/sessions/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
    defaultRequestOptions,
  )
}

export async function generatePdfDocumentSummary(fileId: string): Promise<PdfDocumentSummary> {
  const response = await requestJson<GeneratePdfSummaryResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/summary/generate`,
    { method: 'POST' },
    defaultRequestOptions,
  )
  return toDocumentSummary(response.summary)
}

export async function listPdfModelSettings(): Promise<PdfModelSetting[]> {
  const response = await requestJson<ListPdfModelSettingsResponse>(
    '/api/pdf/model-settings',
    {},
    defaultRequestOptions,
  )
  return response.settings.map(toModelSetting)
}

export async function updatePdfModelSetting(
  settingId: string,
  updates: Pick<PdfModelSetting, 'selectedProvider' | 'selectedModel'>,
): Promise<PdfModelSetting[]> {
  const response = await requestJson<ListPdfModelSettingsResponse>(
    `/api/pdf/model-settings/${encodeURIComponent(settingId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selected_provider: updates.selectedProvider,
        selected_model: updates.selectedModel,
      }),
    },
    defaultRequestOptions,
  )
  return response.settings.map(toModelSetting)
}

function toManagedFile(file: PdfFileResponse): PdfManagedFile {
  return {
    id: file.file_id,
    parentId: file.parent_id ?? undefined,
    kind: file.kind,
    name: file.display_name || file.original_filename,
    createdAt: file.created_at,
    updatedAt: file.updated_at,
    modifiedLabel: formatDateLabel(file.updated_at),
    sizeLabel: file.kind === 'folder' ? 'Folder' : formatBytes(file.size_bytes),
    status: normalizeManagedStatus(file.processing_status),
    progress: file.progress,
    statusDetail: file.status_detail,
    pageCount: file.page_count ?? undefined,
    chunkCount: file.chunk_count ?? undefined,
    errorMessage: file.error_message ?? undefined,
    qualityStatus: normalizeParseQualityStatus(file.quality_status),
    coverageRatio: file.coverage_ratio ?? undefined,
    warningCount: file.warning_count ?? undefined,
    failedPageCount: file.failed_page_count ?? undefined,
    parserBackend: file.parser_backend ?? undefined,
    visibleToMembers: file.visible_to_members,
  }
}

function toParserStatus(status: PdfParserStatusResponse): PdfParserStatus {
  return {
    backend: status.backend,
    available: status.available,
    command: status.command ?? undefined,
    version: status.version ?? undefined,
    detail: status.detail,
  }
}

function toParserProfiles(response: ListPdfParserProfilesResponse): PdfParserProfiles {
  return {
    selectedProfileId: response.selected_profile_id,
    profiles: response.profiles.map(toParserProfile),
  }
}

function toParserProfile(profile: PdfParserProfileResponse): PdfParserProfile {
  return {
    id: profile.id,
    label: profile.label,
    kind: profile.kind,
    backend: profile.backend,
    available: profile.available,
    command: profile.command ?? undefined,
    version: profile.version ?? undefined,
    detail: profile.detail,
    description: profile.description,
    isDefault: profile.is_default,
    isSelected: profile.is_selected,
  }
}

function uploadPathForFile(file: File): string {
  const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath
  return relativePath?.trim() || file.name
}

function toUploadTask(task: PdfUploadTaskResponse): PdfUploadTask {
  return {
    id: task.task_id,
    batchId: task.batch_id ?? undefined,
    fileName: task.original_filename,
    status: normalizeUploadTaskStatus(task.status),
    stage: normalizeUploadTaskStage(task.stage),
    progress: task.progress,
    detail: task.detail,
    errorMessage: task.error_message ?? undefined,
    errorCode: task.error_code ?? undefined,
    parserBackend: task.parser_backend || 'unknown',
    retryCount: task.retry_count,
    fileId: task.file_id ?? undefined,
  }
}

function toSummaryTask(task: PdfSummaryTaskResponse): PdfSummaryTask {
  return {
    id: task.task_id,
    fileId: task.file_id,
    status: normalizeSummaryTaskStatus(task.status),
    progress: task.progress,
    detail: task.detail,
    errorMessage: task.error_message ?? undefined,
    retryCount: task.retry_count,
    result: task.result ?? {},
    createdAt: task.created_at,
    updatedAt: task.updated_at,
    startedAt: task.started_at ?? undefined,
    finishedAt: task.finished_at ?? undefined,
    lastRetryAt: task.last_retry_at ?? undefined,
  }
}

function toUploadBatch(batch: PdfUploadBatchResponse): PdfUploadBatch {
  return {
    id: batch.batch_id,
    sourceName: batch.source_name,
    status: batch.status,
    totalFiles: batch.total_files,
    acceptedFiles: batch.accepted_files,
    skippedFiles: batch.skipped_files,
    totalBytes: batch.total_bytes,
    progress: batch.progress,
    detail: batch.detail,
    errorMessage: batch.error_message ?? undefined,
    parserBackend: batch.parser_backend || 'unknown',
    result: batch.result,
    skippedFilesDetail: toUploadSkippedFiles(batch.result),
    createdLabel: formatDateLabel(batch.created_at),
    updatedLabel: formatDateLabel(batch.updated_at),
  }
}

function toUploadSkippedFiles(result: Record<string, unknown>): PdfUploadSkippedFile[] {
  const rawItems = result.skipped_files_detail
  if (!Array.isArray(rawItems)) {
    return []
  }
  return rawItems
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return null
      }
      const record = item as Record<string, unknown>
      return {
        filename: toOptionalString(record.filename),
        relativePath: toOptionalString(record.relative_path),
        sizeBytes: toOptionalNumber(record.size_bytes),
        reason: toOptionalString(record.reason),
      }
    })
    .filter((item): item is PdfUploadSkippedFile => {
      return Boolean(item?.filename && item.reason)
    })
}

function toOptionalString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function toOptionalNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function toDocumentDetail(response: PdfDocumentDetailResponse): PdfDocumentDetail {
  return {
    fileId: response.file_id,
    summary: toDocumentSummary(response.summary),
    previewBlocks: response.preview_blocks.map(toPreviewBlock),
    schema: response.schema.map(toSchemaItem),
    tags: response.tags,
    parseReport: response.parse_report ? toParseReport(response.parse_report) : undefined,
  }
}

function toDocumentSummary(summary: PdfDocumentSummaryResponse): PdfDocumentSummary {
  return {
    fileId: summary.file_id,
    status: summary.status,
    content: summary.content,
    updatedLabel: summary.updated_at ? formatDateLabel(summary.updated_at) : undefined,
    errorMessage: summary.error_message ?? undefined,
    documentTitle: summary.document_title,
    documentType: summary.document_type,
    businessDomain: summary.business_domain,
    keyTopics: summary.key_topics ?? [],
    positiveRoutingTerms: summary.positive_routing_terms ?? [],
    negativeRoutingTerms: summary.negative_routing_terms ?? [],
    exactIdentifiers: summary.exact_identifiers ?? [],
    suitableQuestions: summary.suitable_questions ?? [],
    unsuitableQuestions: summary.unsuitable_questions ?? [],
    routingNotes: summary.routing_notes,
  }
}

function toPreviewBlock(block: PdfPreviewBlockResponse): PdfDocumentPreviewBlock {
  return {
    id: block.block_id,
    pageLabel: block.page_label,
    title: block.title,
    content: block.content,
  }
}

function toSchemaItem(item: PdfSchemaItemResponse): PdfDocumentSchemaItem {
  return {
    id: item.item_id,
    label: item.label,
    value: item.value,
  }
}

function toParseReport(report: PdfParseReportResponse): PdfParseReport {
  return {
    fileId: report.file_id,
    parserBackend: report.parser_backend,
    parserVersion: report.parser_version ?? undefined,
    qualityStatus: normalizeParseQualityStatus(report.quality_status) ?? 'unknown',
    totalPages: report.total_pages,
    parsedPages: report.parsed_pages,
    failedPages: report.failed_pages,
    emptyPages: report.empty_pages,
    textBlockCount: report.text_block_count,
    tableBlockCount: report.table_block_count,
    imageBlockCount: report.image_block_count,
    chunkCount: report.chunk_count,
    coverageRatio: report.coverage_ratio,
    warningCount: report.warning_count,
    errorCount: report.error_count,
    warnings: report.warnings,
    startedAt: report.started_at ?? undefined,
    finishedAt: report.finished_at ?? undefined,
    createdAt: report.created_at,
    updatedAt: report.updated_at,
    pages: report.pages.map(toParsePage),
    artifacts: report.artifacts.map(toParseArtifact),
  }
}

function toParsePage(page: PdfParsePageResponse): PdfParsePage {
  return {
    id: page.page_id,
    pageNumber: page.page_number,
    pageLabel: page.page_label,
    status: normalizeParsePageStatus(page.status),
    textBlockCount: page.text_block_count,
    tableBlockCount: page.table_block_count,
    imageBlockCount: page.image_block_count,
    charCount: page.char_count,
    warningMessage: page.warning_message ?? undefined,
    errorMessage: page.error_message ?? undefined,
  }
}

function toParseArtifact(artifact: PdfParseArtifactResponse): PdfParseArtifact {
  return {
    id: artifact.artifact_id,
    artifactType: artifact.artifact_type,
    name: artifact.name,
    path: artifact.path ?? undefined,
    sizeBytes: artifact.size_bytes,
    contentHash: artifact.content_hash ?? undefined,
    createdAt: artifact.created_at,
  }
}

function toDocumentChunk(chunk: PdfDocumentChunkResponse): PdfDocumentChunk {
  return {
    id: chunk.chunk_id,
    index: chunk.chunk_index,
    text: chunk.text,
    pageLabel: chunk.page_label ?? undefined,
    title: chunk.title,
    tokenCount: chunk.token_count,
    contentHash: chunk.content_hash,
    metadata: chunk.metadata,
  }
}

function toChunkSearchMatch(match: PdfChunkSearchMatchResponse): PdfChunkSearchMatch {
  return {
    file: toManagedFile(match.file),
    chunk: toDocumentChunk(match.chunk),
    score: match.score,
    excerpt: match.excerpt,
    matchedTerms: match.matched_terms,
  }
}

function toPdfChatAnswer(response: PdfChatAnswerResponse): PdfChatAnswer {
  return {
    sessionId: response.session_id ?? undefined,
    question: response.question,
    answerBlocks: response.answer_blocks.map(toPdfAnswerBlock),
    citations: response.citations.map(toPdfAnswerCitation),
    retrievalMatches: response.retrieval_matches.map(toChunkSearchMatch),
    selectedDocuments: (response.selected_documents ?? []).map(toPdfSelectedDocument),
    newlyAttachedDocuments: (response.newly_attached_documents ?? []).map(
      toPdfSelectedDocument,
    ),
    attachedDocuments: (response.attached_documents ?? []).map(toPdfAttachedDocument),
    insufficientEvidence: response.insufficient_evidence,
    followUpSuggestions: response.follow_up_suggestions,
    warnings: response.warnings,
    createdAt: response.created_at,
  }
}

function toPdfSelectedDocument(
  document: PdfSelectedDocumentResponse,
): PdfSelectedDocument {
  return {
    fileId: document.file_id,
    versionId: document.version_id,
    reason: document.reason,
    confidence: document.confidence ?? undefined,
  }
}

function toPdfAttachedDocument(
  document: PdfAttachedDocumentResponse,
): PdfAttachedDocument {
  return {
    fileId: document.file_id,
    attachedAt: document.attached_at,
    chunkCount: document.chunk_count,
    contextHash: document.context_hash,
    status: document.status,
  }
}

function toPdfChatSession(response: PdfChatSessionResponse): PdfChatSession {
  return {
    sessionId: response.session_id,
    userId: response.user_id,
    title: response.title,
    pinnedAt: response.pinned_at ?? undefined,
    status: response.status,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function toPdfChatTurn(response: PdfChatTurnResponse): PdfChatTurn {
  return {
    turnId: response.turn_id,
    sessionId: response.session_id,
    question: response.question,
    answer: toPdfChatAnswer(response.answer),
    createdAt: response.created_at,
  }
}

function toPdfAnswerBlock(block: PdfChatAnswerBlockResponse): PdfAnswerBlock {
  return {
    text: block.text,
    citationIds: block.citation_ids,
    reasoning: block.reasoning,
  }
}

function toPdfAnswerCitation(citation: PdfCitationResponse): PdfAnswerCitation {
  return {
    citationId: citation.citation_id,
    evidenceId: citation.evidence_id,
    fileId: citation.file_id,
    fileName: citation.file_name,
    chunkId: citation.chunk_id,
    chunkIndex: citation.chunk_index,
    pageLabel: citation.page_label ?? undefined,
    title: citation.title,
    quote: citation.quote,
  }
}

function toModelSetting(setting: PdfModelSettingResponse): PdfModelSetting {
  return {
    id: setting.id,
    label: setting.label,
    providers: setting.providers,
    models: setting.models,
    providerModels: setting.provider_models ?? {},
    selectedProvider: setting.selected_provider,
    selectedModel: setting.selected_model,
  }
}

function normalizeManagedStatus(status: string): PdfManagedFileStatus {
  if (
    status === 'indexed' ||
    status === 'ready' ||
    status === 'uploading' ||
    status === 'queued' ||
    status === 'parsing' ||
    status === 'indexing' ||
    status === 'partial' ||
    status === 'failed'
  ) {
    return status
  }
  return 'queued'
}

function normalizeParseQualityStatus(
  status: string | null | undefined,
): PdfParseQualityStatus | undefined {
  if (
    status === 'unknown' ||
    status === 'good' ||
    status === 'warning' ||
    status === 'partial' ||
    status === 'failed'
  ) {
    return status
  }
  return undefined
}

function normalizeParsePageStatus(status: string): PdfParsePageStatus {
  if (
    status === 'parsed' ||
    status === 'empty' ||
    status === 'image_only' ||
    status === 'failed' ||
    status === 'skipped'
  ) {
    return status
  }
  return 'skipped'
}

function normalizeUploadTaskStatus(status: string): PdfUploadTaskStatus {
  if (
    status === 'uploading' ||
    status === 'queued' ||
    status === 'parsing' ||
    status === 'indexing' ||
    status === 'ready' ||
    status === 'failed' ||
    status === 'cancelled'
  ) {
    return status
  }
  return 'queued'
}

function normalizeSummaryTaskStatus(status: string): PdfSummaryTaskStatus {
  if (
    status === 'queued' ||
    status === 'running' ||
    status === 'ready' ||
    status === 'failed' ||
    status === 'skipped' ||
    status === 'cancelled'
  ) {
    return status
  }
  return 'failed'
}

function normalizeUploadTaskStage(stage: string): PdfUploadTask['stage'] {
  if (
    stage === 'queued' ||
    stage === 'claimed' ||
    stage === 'parsing' ||
    stage === 'indexing' ||
    stage === 'ready' ||
    stage === 'failed' ||
    stage === 'cancelled'
  ) {
    return stage
  }
  return 'queued'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDateLabel(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Updated recently'
  }
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
