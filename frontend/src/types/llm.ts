export interface LlmModelDefaults {
  summary_provider: string
  summary_model: string
  router_provider: string
  router_model: string
  answer_provider: string
  answer_model: string
}

export interface LlmProviderOption {
  provider: string
  label: string
  models: string[]
}

export interface LlmModelOptionsResponse {
  models: string[]
  providers: LlmProviderOption[]
  defaults: LlmModelDefaults
}

export interface LlmPreference extends LlmModelDefaults {
  scope: string
  created_at: string
  updated_at: string
}
