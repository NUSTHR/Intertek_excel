export type ModelStageId = 'summary' | 'router' | 'answer'

/**
 * A single stage in the model configuration card. Each stage has its own
 * provider/model pair that may be edited independently. All edits are
 * autosaved — there is no explicit "Set Default" button in the unified UI.
 */
export interface ModelStage {
  id: ModelStageId
  label: string
  provider: string
  model: string
  providers: string[]
  modelsForProvider: Record<string, string[]>
  isDirty: boolean
  isSaving: boolean
  errorMessage: string
}

export interface ModelPreferenceFieldErrors {
  provider?: string
  model?: string
}
