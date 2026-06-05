export interface LlmModelDefaults {
  summary_model: string
  router_model: string
  answer_model: string
}

export interface LlmModelOptionsResponse {
  models: string[]
  defaults: LlmModelDefaults
}
