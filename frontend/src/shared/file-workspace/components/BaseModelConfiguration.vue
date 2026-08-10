<script setup lang="ts">
import BaseInsightSectionCard from './BaseInsightSectionCard.vue'
import type { BaseModelStageViewModel } from '../model-configuration-contract'
import { fileWorkspaceCopy } from '../copy'

withDefaults(defineProps<{
  stages: BaseModelStageViewModel[]
  disabled?: boolean
  isSaving?: boolean
  feedback?: string
  feedbackTone?: 'neutral' | 'success' | 'error'
}>(), {
  disabled: false,
  isSaving: false,
  feedback: '',
  feedbackTone: 'neutral',
})

const emit = defineEmits<{
  change: [stageId: string, field: 'provider' | 'model', value: string]
}>()

function selectValue(event: Event): string {
  return event.target instanceof HTMLSelectElement ? event.target.value : ''
}
</script>

<template>
  <BaseInsightSectionCard
    class="file-workspace-base-reference-card"
    :title="fileWorkspaceCopy.modelConfiguration"
    icon-name="tune"
    collapsible
  >
    <div class="file-workspace-base-model-grid">
      <div v-for="stage in stages" :key="stage.id" class="file-workspace-base-model-row">
        <label :for="`provider-${stage.id}`">{{ stage.label }}</label>
        <select
          :id="`provider-${stage.id}`"
          :value="stage.provider"
          :disabled="disabled"
          :aria-invalid="Boolean(stage.errorMessage)"
          @change="emit('change', stage.id, 'provider', selectValue($event))"
        >
          <option v-for="option in stage.providers" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <select
          :id="`model-${stage.id}`"
          :value="stage.model"
          :disabled="disabled"
          :aria-label="`${stage.label} model`"
          :aria-invalid="Boolean(stage.errorMessage)"
          @change="emit('change', stage.id, 'model', selectValue($event))"
        >
          <option
            v-for="option in stage.models"
            :key="option.value"
            :value="option.value"
            :disabled="option.disabled"
          >{{ option.label }}</option>
        </select>
        <small v-if="stage.errorMessage" class="file-workspace-base-field-error">
          {{ stage.errorMessage }}
        </small>
      </div>
    </div>
    <p
      class="file-workspace-base-save-status"
      :data-tone="feedbackTone"
      role="status"
      aria-live="polite"
    >
      {{ isSaving ? 'Saving changes…' : feedback || 'Changes save automatically.' }}
    </p>
  </BaseInsightSectionCard>
</template>
