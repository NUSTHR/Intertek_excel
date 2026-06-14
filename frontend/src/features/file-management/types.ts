import type { ModelStage } from '../../app/workspace-types'

export type ModelPreferenceFeedbackKind = 'success' | 'error'

export interface ModelStageDraft {
  stage: ModelStage
  label: string
  provider: string
  model: string
  modelOptions: string[]
}

export interface FileSchemaColumn {
  key: string
  label: string
  sourceName: string
  type: string
  sample: string
}
