export interface SheetSummary {
  sheet_id: string
  sheet_name: string
  summary: string
  important_columns: string[]
  likely_question_types: string[]
  header_terms: string[]
  sampled_identifiers: string[]
}

export interface DocumentSummary {
  summary_id: string
  file_id: string
  version_id: string
  document_title: string
  document_type: string
  summary_text: string
  business_domain: string
  coverage_scope: Record<string, string[]>
  key_topics: string[]
  positive_routing_terms: string[]
  negative_routing_terms: string[]
  exact_identifiers: string[]
  suitable_questions: string[]
  unsuitable_questions: string[]
  sheet_summaries: SheetSummary[]
  routing_notes: string
  created_at: string
}

export interface SheetSummaryUpdate {
  sheet_id: string
  sheet_name: string
  summary: string
  important_columns: string[]
  likely_question_types: string[]
  header_terms: string[]
  sampled_identifiers: string[]
}

export interface DocumentSummaryUpdate {
  summary_text?: string
  business_domain?: string
  key_topics?: string[]
  positive_routing_terms?: string[]
  negative_routing_terms?: string[]
  exact_identifiers?: string[]
  suitable_questions?: string[]
  unsuitable_questions?: string[]
  sheet_summaries?: SheetSummaryUpdate[]
  routing_notes?: string
}
