<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import DocumentSummaryCard from '../../../components/DocumentSummaryCard.vue'

import type { DocumentSummary, DocumentSummaryUpdate } from '../../../types/document-summary'
import type { LlmProviderOption } from '../../../types/llm'
import type { ModelStage } from '../../../app/workspace-types'
import type { ModelPreferenceFeedbackKind, ModelStageDraft } from '../types'

defineProps<{
  modelStages: ModelStageDraft[]
  providers: LlmProviderOption[]
  modelPreferenceFeedback: string
  modelPreferenceFeedbackKind: ModelPreferenceFeedbackKind
  canSaveModelPreference: boolean
  isModelPreferenceSaving: boolean
  summary: DocumentSummary | null
  isSummaryGenerating: boolean
  isSummarySaving: boolean
  canGenerateSummary: boolean
}>()

const emit = defineEmits<{
  providerChange: [stage: ModelStage, provider: string]
  modelChange: [stage: ModelStage, model: string]
  saveModelPreference: []
  generateSummary: []
  saveSummary: [update: DocumentSummaryUpdate, onSaved: (saved: boolean) => void]
}>()

function readSelectValue(event: Event): string {
  return event.target instanceof HTMLSelectElement ? event.target.value : ''
}
</script>

<template>
  <section class="file-summary-stack">
    <article v-if="providers.length > 0" class="model-config-card">
      <div class="config-heading">
        <div>
          <span class="config-icon"><AppIcon name="tune" /></span>
          <h3>Model Settings</h3>
        </div>
      </div>
      <div class="model-config-grid">
        <div v-for="stage in modelStages" :key="stage.stage" class="model-setting-row">
          <span>{{ stage.label }}</span>
          <select
            :value="stage.provider"
            @change="emit('providerChange', stage.stage, readSelectValue($event))"
          >
            <option
              v-for="provider in providers"
              :key="`${stage.stage}-provider-${provider.provider}`"
              :value="provider.provider"
            >
              {{ provider.label }}
            </option>
          </select>
          <select
            :value="stage.model"
            @change="emit('modelChange', stage.stage, readSelectValue($event))"
          >
            <option
              v-for="model in stage.modelOptions"
              :key="`${stage.stage}-model-${model}`"
              :value="model"
            >
              {{ model }}
            </option>
          </select>
        </div>
      </div>
      <div class="model-config-actions">
        <p
          v-if="modelPreferenceFeedback"
          class="model-config-feedback"
          :class="modelPreferenceFeedbackKind"
        >
          {{ modelPreferenceFeedback }}
        </p>
        <button
          type="button"
          class="model-save-button"
          :disabled="!canSaveModelPreference || isModelPreferenceSaving"
          @click="emit('saveModelPreference')"
        >
          <AppIcon name="check" />
          <span>{{ isModelPreferenceSaving ? 'Saving' : 'Set Default' }}</span>
        </button>
      </div>
    </article>

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
