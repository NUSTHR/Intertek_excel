export interface ModelSelectOption {
  value: string
  label: string
  disabled?: boolean
}

export interface BaseModelStageViewModel {
  id: string
  label: string
  provider: string
  model: string
  providers: ModelSelectOption[]
  models: ModelSelectOption[]
  errorMessage?: string
}
