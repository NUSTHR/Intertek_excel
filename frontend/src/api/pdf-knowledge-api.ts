import { defaultRequestOptions } from './config'
import { requestJson } from './errors'
import type {
  PdfAnswerBlock,
  PdfAnswerCitation,
  PdfChunkSearchMatch,
  PdfChunkSearchResult,
  PdfChatAnswer,
  PdfDocumentChunk,
  PdfDocumentDetail,
  PdfDocumentPreviewBlock,
  PdfDocumentSchemaItem,
  PdfDocumentSummary,
  PdfManagedFile,
  PdfManagedFileKind,
  PdfManagedFileStatus,
  PdfModelSetting,
  PdfParserStatus,
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

interface PdfUploadTaskResponse {
  task_id: string
  file_id: string | null
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

interface CreatePdfUploadTasksResponse {
  tasks: PdfUploadTaskResponse[]
}

interface ListPdfUploadTasksResponse {
  tasks: PdfUploadTaskResponse[]
}

interface PdfDocumentSummaryResponse {
  file_id: string
  status: PdfDocumentSummary['status']
  content: string
  updated_at: string | null
  error_message: string | null
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

interface PdfDocumentDetailResponse {
  file_id: string
  summary: PdfDocumentSummaryResponse
  preview_blocks: PdfPreviewBlockResponse[]
  schema: PdfSchemaItemResponse[]
  tags: string[]
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

interface PdfChatAnswerResponse {
  question: string
  answer_blocks: PdfChatAnswerBlockResponse[]
  citations: PdfCitationResponse[]
  retrieval_matches: PdfChunkSearchMatchResponse[]
  insufficient_evidence: boolean
  follow_up_suggestions: string[]
  warnings: string[]
  created_at: string
}

interface GeneratePdfSummaryResponse {
  summary: PdfDocumentSummaryResponse
}

interface PdfModelSettingResponse {
  id: string
  label: string
  providers: string[]
  models: string[]
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

export async function getPdfParserStatus(): Promise<PdfParserStatus> {
  const response = await requestJson<PdfParserStatusResponse>(
    '/api/pdf/parser/status',
    {},
    defaultRequestOptions,
  )
  return toParserStatus(response)
}

export async function listPdfUploadTasks(): Promise<PdfUploadTask[]> {
  const response = await requestJson<ListPdfUploadTasksResponse>(
    '/api/pdf/files/upload-tasks',
    {},
    defaultRequestOptions,
  )
  return response.tasks.map(toUploadTask)
}

export async function createPdfUploadTask(files: File[]): Promise<PdfUploadTask[]> {
  const body = new FormData()
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
  return response.tasks.map(toUploadTask)
}

export async function getPdfDocumentDetail(fileId: string): Promise<PdfDocumentDetail> {
  const response = await requestJson<PdfDocumentDetailResponse>(
    `/api/pdf/files/${encodeURIComponent(fileId)}/detail`,
    {},
    defaultRequestOptions,
  )
  return toDocumentDetail(response)
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
  fileIds?: string[]
  retrievalLimit?: number
  enableDeepThinking?: boolean
}): Promise<PdfChatAnswer> {
  const response = await requestJson<PdfChatAnswerResponse>(
    '/api/pdf/chat',
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
      ...defaultRequestOptions,
      timeoutMs: Math.max(defaultRequestOptions.timeoutMs ?? 30000, 120000),
      timeoutMessage: 'PDF answer generation is still running. Please try again shortly.',
    },
  )
  return toPdfChatAnswer(response)
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
    modifiedLabel: formatDateLabel(file.updated_at),
    sizeLabel: file.kind === 'folder' ? 'Folder' : formatBytes(file.size_bytes),
    status: normalizeManagedStatus(file.processing_status),
    progress: file.progress,
    statusDetail: file.status_detail,
    pageCount: file.page_count ?? undefined,
    chunkCount: file.chunk_count ?? undefined,
    errorMessage: file.error_message ?? undefined,
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

function uploadPathForFile(file: File): string {
  const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath
  return relativePath?.trim() || file.name
}

function toUploadTask(task: PdfUploadTaskResponse): PdfUploadTask {
  return {
    id: task.task_id,
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

function toDocumentDetail(response: PdfDocumentDetailResponse): PdfDocumentDetail {
  return {
    fileId: response.file_id,
    summary: toDocumentSummary(response.summary),
    previewBlocks: response.preview_blocks.map(toPreviewBlock),
    schema: response.schema.map(toSchemaItem),
    tags: response.tags,
  }
}

function toDocumentSummary(summary: PdfDocumentSummaryResponse): PdfDocumentSummary {
  return {
    fileId: summary.file_id,
    status: summary.status,
    content: summary.content,
    updatedLabel: summary.updated_at ? formatDateLabel(summary.updated_at) : undefined,
    errorMessage: summary.error_message ?? undefined,
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
    question: response.question,
    answerBlocks: response.answer_blocks.map(toPdfAnswerBlock),
    citations: response.citations.map(toPdfAnswerCitation),
    retrievalMatches: response.retrieval_matches.map(toChunkSearchMatch),
    insufficientEvidence: response.insufficient_evidence,
    followUpSuggestions: response.follow_up_suggestions,
    warnings: response.warnings,
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
    status === 'failed'
  ) {
    return status
  }
  return 'queued'
}

function normalizeUploadTaskStatus(status: string): PdfUploadTaskStatus {
  if (
    status === 'uploading' ||
    status === 'queued' ||
    status === 'parsing' ||
    status === 'indexing' ||
    status === 'ready' ||
    status === 'failed'
  ) {
    return status
  }
  return 'queued'
}

function normalizeUploadTaskStage(stage: string): PdfUploadTask['stage'] {
  if (
    stage === 'queued' ||
    stage === 'claimed' ||
    stage === 'parsing' ||
    stage === 'indexing' ||
    stage === 'ready' ||
    stage === 'failed'
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
