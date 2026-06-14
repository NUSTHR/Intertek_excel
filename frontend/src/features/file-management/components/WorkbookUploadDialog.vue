<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'

import type { UploadDialog } from '../../../app/workspace-types'
import type { UploadTaskResponse } from '../../../types/excel-assets'

const props = defineProps<{
  dialog: UploadDialog
  errorMessage: string
  isBusy: boolean
  task: UploadTaskResponse | null
}>()

defineEmits<{
  cancel: []
  confirm: []
}>()

const taskStatusCopy: Record<string, { title: string; detail: string }> = {
  queued: {
    title: 'Queued',
    detail: 'Waiting for an upload worker to start parsing.',
  },
  processing: {
    title: 'Processing',
    detail: 'Parsing workbook sheets and preparing searchable rows.',
  },
  failed: {
    title: 'Failed',
    detail: 'The workbook could not be parsed.',
  },
  ready: {
    title: 'Complete',
    detail: 'Workbook parsing is complete.',
  },
}

const canCancel = computed(() => !props.task || props.task.status === 'failed')

const primaryLabel = computed(() => {
  if (props.task) {
    return 'Processing...'
  }
  if (props.isBusy) {
    return 'Starting...'
  }
  return props.dialog.kind === 'replace' ? 'Replace' : 'Upload'
})

const taskTitle = computed(() => {
  if (!props.task) {
    return ''
  }
  return taskStatusCopy[props.task.status]?.title ?? props.task.status
})

const taskDetail = computed(() => {
  if (!props.task) {
    return ''
  }
  return taskStatusCopy[props.task.status]?.detail ?? ''
})
</script>

<template>
  <section
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="upload-dialog-title"
    @keydown.esc="canCancel ? $emit('cancel') : undefined"
  >
    <div class="app-dialog upload-confirm-dialog">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">
            {{ dialog.kind === 'replace' ? 'Replacement' : 'Upload' }}
          </p>
          <h3 id="upload-dialog-title">
            {{ dialog.kind === 'replace' ? 'Confirm replacement' : 'Upload and parse' }}
          </h3>
        </div>
        <button
          type="button"
          class="dialog-icon-button"
          aria-label="Close"
          :disabled="!canCancel"
          @click="$emit('cancel')"
        >
          <AppIcon name="close" />
        </button>
      </div>
      <div class="upload-dialog-file">
        <span class="file-badge large"><AppIcon name="table_chart" /></span>
        <div>
          <strong>{{ dialog.file.name }}</strong>
          <span>{{
            dialog.kind === 'replace'
              ? 'Create a new active version'
              : 'Parse workbook into searchable sheets'
          }}</span>
        </div>
      </div>
      <p v-if="dialog.kind === 'replace'" class="dialog-copy">
        A file with this name already exists. Confirming will keep the workbook record and create a new active version.
      </p>
      <div
        v-if="task"
        class="upload-task-status"
        :class="`status-${task.status}`"
        role="status"
        aria-live="polite"
      >
        <div class="upload-task-row">
          <span class="upload-task-spinner" aria-hidden="true">
            <AppIcon :name="task.status === 'failed' ? 'close' : 'refresh'" />
          </span>
          <div>
            <strong>{{ taskTitle }}</strong>
            <span>{{ taskDetail }}</span>
          </div>
        </div>
        <div class="upload-task-meter" aria-hidden="true">
          <span></span>
        </div>
      </div>
      <p v-if="errorMessage" class="dialog-error">{{ errorMessage }}</p>
      <div class="dialog-actions">
        <button
          type="button"
          class="dialog-secondary"
          :disabled="!canCancel"
          @click="$emit('cancel')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="dialog-primary"
          :disabled="isBusy || Boolean(task)"
          @click="$emit('confirm')"
        >
          {{ primaryLabel }}
        </button>
      </div>
    </div>
  </section>
</template>
