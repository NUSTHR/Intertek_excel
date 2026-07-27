export type PdfSidebarView = 'knowledge' | 'chats'

export type PdfWorkspaceMode = 'management' | 'chat'

export type PdfManagementInsightTab = 'summary' | 'preview' | 'schema'

export type PdfKnowledgeNodeKind = 'folder' | 'pdf' | 'table'

export interface PdfKnowledgeNode {
  id: string
  name: string
  kind: PdfKnowledgeNodeKind
  active?: boolean
  children?: PdfKnowledgeNode[]
}

export interface PdfRecentChat {
  id: string
  title: string
  pinnedAt?: string
}

export interface PdfBreadcrumbItem {
  id: string
  label: string
  icon?: string
  active?: boolean
}

export interface PdfChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  bullets?: PdfChatBullet[]
  quote?: string
  closing?: string
  citationIds?: string[]
  insufficientEvidence?: boolean
  error?: boolean
}

export interface PdfChatBullet {
  title: string
  text: string
}

export type PdfCitationTone = 'primary' | 'supporting' | 'crossReference'

export interface PdfCitation {
  id: string
  sourceLabel: string
  fileName: string
  fileKind: PdfKnowledgeNodeKind
  matchLabel: string
  excerpt: string
  location: string
  tone: PdfCitationTone
}

export type PdfManagedFileKind = 'folder' | 'pdf' | 'csv' | 'xlsx'

export type PdfManagedFileStatus =
  | 'indexed'
  | 'ready'
  | 'uploading'
  | 'queued'
  | 'parsing'
  | 'indexing'
  | 'partial'
  | 'failed'
  | 'cancelled'

export type PdfUploadTaskStatus =
  | 'uploading'
  | 'queued'
  | 'parsing'
  | 'indexing'
  | 'ready'
  | 'failed'
  | 'cancelled'

export type PdfSummaryTaskStatus =
  | 'queued'
  | 'running'
  | 'ready'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export type PdfUploadTaskStage =
  | 'queued'
  | 'claimed'
  | 'parsing'
  | 'indexing'
  | 'ready'
  | 'failed'
  | 'cancelled'

export type PdfUploadBatchStatus =
  | 'queued'
  | 'processing'
  | 'ready'
  | 'partial'
  | 'failed'
  | 'cancelled'

export interface PdfManagedFile {
  id: string
  parentId?: string
  kind: PdfManagedFileKind
  name: string
  modifiedLabel: string
  sizeLabel: string
  status: PdfManagedFileStatus
  progress?: number
  statusDetail?: string
  pageCount?: number
  chunkCount?: number
  errorMessage?: string
  qualityStatus?: PdfParseQualityStatus
  coverageRatio?: number
  warningCount?: number
  failedPageCount?: number
  parserBackend?: string
  visibleToMembers: boolean
  active?: boolean
}

export interface PdfChatSession {
  sessionId: string
  userId: string
  title: string
  pinnedAt?: string
  status: string
  createdAt: string
  updatedAt: string
}

export interface PdfUploadTask {
  id: string
  batchId?: string
  fileName: string
  status: PdfUploadTaskStatus
  stage: PdfUploadTaskStage
  progress: number
  detail: string
  errorMessage?: string
  errorCode?: string
  parserBackend: string
  retryCount: number
  fileId?: string
}

export interface PdfSummaryTask {
  id: string
  fileId: string
  status: PdfSummaryTaskStatus
  progress: number
  detail: string
  errorMessage?: string
  retryCount: number
  result: Record<string, unknown>
  createdAt: string
  updatedAt: string
  startedAt?: string
  finishedAt?: string
  lastRetryAt?: string
}

export interface PdfUploadBatch {
  id: string
  sourceName: string
  status: PdfUploadBatchStatus
  totalFiles: number
  acceptedFiles: number
  skippedFiles: number
  totalBytes: number
  progress: number
  detail: string
  errorMessage?: string
  parserBackend: string
  result: Record<string, unknown>
  skippedFilesDetail: PdfUploadSkippedFile[]
  createdLabel: string
  updatedLabel: string
}

export interface PdfUploadSkippedFile {
  filename: string
  relativePath: string
  sizeBytes: number
  reason: string
}

export interface PdfUploadCreationResult {
  batch?: PdfUploadBatch
  tasks: PdfUploadTask[]
}

export interface PdfManagementNavItem {
  id: PdfWorkspaceMode | 'knowledge' | 'diagnostics'
  label: string
  icon: string
  active?: boolean
}

export interface PdfModelSetting {
  id: string
  label: string
  providers: string[]
  models: string[]
  selectedProvider: string
  selectedModel: string
}

export interface PdfParserStatus {
  backend: string
  available: boolean
  command?: string
  version?: string
  detail: string
}

export interface PdfParserProfile {
  id: string
  label: string
  kind: 'local' | 'cloud' | string
  backend: string
  available: boolean
  command?: string
  version?: string
  detail: string
  description: string
  isDefault: boolean
  isSelected: boolean
}

export interface PdfParserProfiles {
  selectedProfileId: string
  profiles: PdfParserProfile[]
}

export interface PdfDocumentSummary {
  fileId: string
  status: 'empty' | 'generating' | 'pending' | 'ready' | 'failed' | 'stale'
  content: string
  updatedLabel?: string
  errorMessage?: string
  documentTitle?: string
  documentType?: string
  businessDomain?: string
  keyTopics?: string[]
  positiveRoutingTerms?: string[]
  negativeRoutingTerms?: string[]
  exactIdentifiers?: string[]
  suitableQuestions?: string[]
  unsuitableQuestions?: string[]
  routingNotes?: string
}

export interface PdfDocumentPreviewBlock {
  id: string
  pageLabel: string
  title: string
  content: string
}

export interface PdfDocumentSchemaItem {
  id: string
  label: string
  value: string
}

export type PdfParseQualityStatus = 'unknown' | 'good' | 'warning' | 'partial' | 'failed'

export type PdfParsePageStatus = 'parsed' | 'empty' | 'image_only' | 'failed' | 'skipped'

export interface PdfParsePage {
  id: string
  pageNumber: number
  pageLabel: string
  status: PdfParsePageStatus
  textBlockCount: number
  tableBlockCount: number
  imageBlockCount: number
  charCount: number
  warningMessage?: string
  errorMessage?: string
}

export interface PdfParseArtifact {
  id: string
  artifactType: string
  name: string
  path?: string
  sizeBytes: number
  contentHash?: string
  createdAt: string
}

export interface PdfParseReport {
  fileId: string
  parserBackend: string
  parserVersion?: string
  qualityStatus: PdfParseQualityStatus
  totalPages: number
  parsedPages: number
  failedPages: number
  emptyPages: number
  textBlockCount: number
  tableBlockCount: number
  imageBlockCount: number
  chunkCount: number
  coverageRatio: number
  warningCount: number
  errorCount: number
  warnings: string[]
  startedAt?: string
  finishedAt?: string
  createdAt: string
  updatedAt: string
  pages: PdfParsePage[]
  artifacts: PdfParseArtifact[]
}

export interface PdfDocumentChunk {
  id: string
  index: number
  text: string
  pageLabel?: string
  title: string
  tokenCount: number
  contentHash: string
  metadata: Record<string, string>
}

export interface PdfDocumentDetail {
  fileId: string
  summary: PdfDocumentSummary
  previewBlocks: PdfDocumentPreviewBlock[]
  schema: PdfDocumentSchemaItem[]
  tags: string[]
  parseReport?: PdfParseReport
}

export interface PdfChunkSearchMatch {
  file: PdfManagedFile
  chunk: PdfDocumentChunk
  score: number
  excerpt: string
  matchedTerms: string[]
}

export interface PdfChunkSearchResult {
  query: string
  matches: PdfChunkSearchMatch[]
  totalMatches: number
  limit: number
}

export interface PdfAnswerBlock {
  text: string
  citationIds: string[]
  reasoning: string
}

export interface PdfAnswerCitation {
  citationId: string
  evidenceId: string
  fileId: string
  fileName: string
  chunkId: string
  chunkIndex: number
  pageLabel?: string
  title: string
  quote: string
}

export interface PdfChatAnswer {
  sessionId?: string
  question: string
  answerBlocks: PdfAnswerBlock[]
  citations: PdfAnswerCitation[]
  retrievalMatches: PdfChunkSearchMatch[]
  selectedDocuments: PdfSelectedDocument[]
  newlyAttachedDocuments: PdfSelectedDocument[]
  attachedDocuments: PdfAttachedDocument[]
  insufficientEvidence: boolean
  followUpSuggestions: string[]
  warnings: string[]
  createdAt: string
}

export interface PdfSelectedDocument {
  fileId: string
  versionId: string
  reason: string
  confidence?: number
}

export interface PdfAttachedDocument {
  fileId: string
  attachedAt: string
  chunkCount: number
  contextHash: string
  status: string
}

export interface PdfChatTurn {
  turnId: string
  sessionId: string
  question: string
  answer: PdfChatAnswer
  createdAt: string
}
