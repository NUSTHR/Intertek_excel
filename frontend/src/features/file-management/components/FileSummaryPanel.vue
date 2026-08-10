<script setup lang="ts">
import { computed } from 'vue'

import DocumentSummaryCard from '../../../components/DocumentSummaryCard.vue'
import BaseModelConfiguration from '../../../shared/file-workspace/components/BaseModelConfiguration.vue'

import type { DocumentSummary, DocumentSummaryUpdate } from '../../../types/document-summary'
import type { LlmProviderOption } from '../../../types/llm'
import type { ModelStage } from '../../../app/workspace-types'
import type { ModelPreferenceFeedbackKind, ModelStageDraft } from '../types'
import type { BaseModelStageViewModel } from '../../../shared/file-workspace/model-configuration-contract'

const props = defineProps<{
  modelStages: ModelStageDraft[]
  providers: LlmProviderOption[]
  modelPreferenceFeedback: string
  modelPreferenceFeedbackKind: ModelPreferenceFeedbackKind
  isModelPreferenceSaving: boolean
  summary: DocumentSummary | null
  isSummaryGenerating: boolean
  isSummarySaving: boolean
  canGenerateSummary: boolean
}>()

const emit = defineEmits<{
  providerChange: [stage: ModelStage, provider: string]
  modelChange: [stage: ModelStage, model: string]
  generateSummary: []
  saveSummary: [update: DocumentSummaryUpdate, onSaved: (saved: boolean) => void]
}>()

const normalizedModelStages = computed<BaseModelStageViewModel[]>(() => props.modelStages.map((stage) => ({
  id: stage.stage,
  label: stage.label,
  provider: stage.provider,
  model: stage.model,
  providers: props.providers.map((provider) => ({
    value: provider.provider,
    label: provider.label,
  })),
  models: stage.modelOptions.map((model) => ({ value: model, label: model })),
})))

function handleModelChange(stageId: string, field: 'provider' | 'model', value: string): void {
  const stage = stageId as ModelStage
  if (field === 'provider') emit('providerChange', stage, value)
  else emit('modelChange', stage, value)
}
</script>

<template>
  <section class="file-summary-stack">
    <BaseModelConfiguration
      v-if="providers.length > 0"
      :stages="normalizedModelStages"
      :is-saving="isModelPreferenceSaving"
      :feedback="modelPreferenceFeedback"
      :feedback-tone="modelPreferenceFeedbackKind"
      @change="handleModelChange"
    />

    <DocumentSummaryCard
      :summary="summary"
      :is-generating="isSummaryGenerating"
      :is-saving="isSummarySaving"
      :can-generate="canGenerateSummary"
      @generate="emit('generateSummary')"
      @save="(update, onSaved) => emit('saveSummary', update, onSaved)"
    />
  </section>
</template>
