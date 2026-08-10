import type { ModelStage } from './file-model-preference-contract'

export type FileSummaryContentKind = 'rich' | 'plain'

export interface FileSummaryContent {
  kind: FileSummaryContentKind
  documentTitle: string
  businessDomain: string
  description: string
}

export interface SummaryTag {
  id: string
  label: string
}

export interface SheetNote {
  sheetId: string
  sheetName: string
  note: string
}

export type FileSummaryTaskStatus =
  | 'queued'
  | 'running'
  | 'ready'
  | 'failed'
  | 'skipped'
  | 'cancelled'

export interface FileSummaryTask {
  id: string
  fileId: string
  status: FileSummaryTaskStatus
  progress: number
  detail: string
  errorMessage?: string
  retryCount: number
}

/**
 * A single field-level edit. Multiple edits emitted in the same call are
 * treated as one atomic save by the host composable.
 */
export type SummaryEditField =
  | 'businessDomain'
  | 'documentTitle'
  | 'description'
  | 'tags'
  | 'goodQuestions'
  | 'outOfScopeQuestions'
  | 'routingNotes'
  | 'sheetNotes'

export interface SummaryEditPatch {
  field: SummaryEditField
  value: string | string[] | SheetNote[]
}

export interface BaseFileSummaryViewModel {
  summary: FileSummaryContent
  tags: SummaryTag[]
  contextTags: SummaryTag[]
  routingSignals: string[]
  goodQuestions: string[]
  outOfScopeQuestions: string[]
  sheetNotes: SheetNote[]
  isGenerating: boolean
  isSaving: boolean
  isEditable: boolean
  supportsBatch: boolean
  selectedFileCount: number
  tasks: FileSummaryTask[]
  modelStages: ModelStage[]
  errorMessage: string
}

export interface BaseFileSummaryEmits {
  generate: []
  cancelTask: [taskId: string]
  retryTask: [taskId: string]
  save: [patches: SummaryEditPatch[]]
  modelChange: [stageId: string, field: 'provider' | 'model', value: string]
  flushRequested: []
}
