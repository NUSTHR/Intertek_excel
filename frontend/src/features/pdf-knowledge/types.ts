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
  | 'failed'

export type PdfUploadTaskStatus = 'uploading' | 'queued' | 'parsing' | 'indexing' | 'ready' | 'failed'

export type PdfUploadTaskStage = 'queued' | 'claimed' | 'parsing' | 'indexing' | 'ready' | 'failed'

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
  active?: boolean
}

export interface PdfUploadTask {
  id: string
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

export interface PdfManagementNavItem {
  id: PdfWorkspaceMode | 'dashboard' | 'files' | 'knowledge'
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

export interface PdfDocumentSummary {
  fileId: string
  status: 'empty' | 'generating' | 'ready' | 'failed'
  content: string
  updatedLabel?: string
  errorMessage?: string
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
  question: string
  answerBlocks: PdfAnswerBlock[]
  citations: PdfAnswerCitation[]
  retrievalMatches: PdfChunkSearchMatch[]
  insufficientEvidence: boolean
  followUpSuggestions: string[]
  warnings: string[]
  createdAt: string
}
