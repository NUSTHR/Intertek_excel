export interface ChatRequest {
  question: string
  session_id?: string | null
  enable_deep_thinking?: boolean
}

export interface ChatSession {
  session_id: string
  created_at: string
  updated_at: string
  title: string
  pinned_at: string | null
  status: string
}

export interface ChatSessionListResponse {
  sessions: ChatSession[]
}

export interface ChatTurn {
  turn_id: string
  session_id: string
  question: string
  answer: ChatAnswer
  created_at: string
}

export interface ChatTurnListResponse {
  turns: ChatTurn[]
}

export interface SelectedDocument {
  file_id: string
  version_id: string
  reason: string
  confidence: number | null
}

export interface ExcelCitation {
  citation_id: string
  evidence_id: string
  file_id: string
  version_id: string
  sheet_id: string
  sheet_name: string
  row_id: string
  row: string[]
  quote: string
}

export interface AttachedDocument {
  file_id: string
  version_id: string
  attached_at: string
  row_count: number
  context_hash: string
  status: string
}

export interface ChatAnswerBlock {
  text: string
  citation_ids: string[]
  reasoning?: string
}

export interface ChatAnswer {
  session_id: string
  question: string
  answer_blocks: ChatAnswerBlock[]
  selected_documents: SelectedDocument[]
  newly_attached_documents: SelectedDocument[]
  attached_documents: AttachedDocument[]
  citations: ExcelCitation[]
  insufficient_evidence: boolean
  follow_up_suggestions: string[]
  warnings: string[]
  created_at: string
}

export interface ChatRouteResult {
  session_id: string
  question: string
  selected_documents: SelectedDocument[]
  newly_attached_documents: SelectedDocument[]
  attached_documents: AttachedDocument[]
  created_at: string
}

export interface ChatModelSelection {
  enableDeepThinking?: boolean
}
