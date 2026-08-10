<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { FileWorkspaceIconName } from '../file-card-contract'
import { fileWorkspaceCopy } from '../copy'

withDefaults(defineProps<{
  subtitle?: string
  actionLabel: string
  actionIcon?: FileWorkspaceIconName
  actionDisabled?: boolean
}>(), {
  subtitle: '',
  actionIcon: 'bolt',
  actionDisabled: false,
})

const emit = defineEmits<{
  generate: []
}>()
</script>

<template>
  <article class="document-summary-card file-workspace-base-card" data-tone="premium">
    <header class="document-summary-head file-workspace-base-card-head">
      <div class="document-summary-title">
        <span class="summary-icon"><AppIcon name="auto_awesome" /></span>
        <div>
          <h3>{{ fileWorkspaceCopy.summaryTitle }}</h3>
          <p v-if="subtitle" :title="subtitle">{{ subtitle }}</p>
        </div>
      </div>
      <div class="summary-head-actions">
        <button
          type="button"
          class="summary-action-button primary file-workspace-base-primary-action"
          :disabled="actionDisabled"
          @click="emit('generate')"
        >
          <AppIcon :name="actionIcon" />
          {{ actionLabel }}
        </button>
        <slot name="actions"></slot>
      </div>
    </header>

    <slot></slot>
  </article>
</template>
