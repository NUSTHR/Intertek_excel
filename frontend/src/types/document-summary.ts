export interface SheetSummary {
  sheet_id: string
  sheet_name: string
  summary: string
  important_columns: string[]
  likely_question_types: string[]
}

export interface DocumentSummary {
  summary_id: string
  file_id: string
  version_id: string
  summary_text: string
  business_domain: string
  key_topics: string[]
  suitable_questions: string[]
  unsuitable_questions: string[]
  sheet_summaries: SheetSummary[]
  created_at: string
}
