<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { ConfirmDialog, RenameDialog } from '../app/workspace-types'

defineProps<{
  renameDialog: RenameDialog | null
  confirmDialog: ConfirmDialog | null
  renameDraft: string
  errorMessage: string
  isBusy: boolean
}>()

const emit = defineEmits<{
  cancel: []
  confirmDelete: []
  submitRename: []
  updateRenameDraft: [value: string]
}>()

function handleRenameInput(event: Event): void {
  emit('updateRenameDraft', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <section
    v-if="renameDialog"
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="rename-dialog-title"
    @click.self="emit('cancel')"
    @keydown.esc="emit('cancel')"
  >
    <form class="app-dialog" @submit.prevent="emit('submitRename')">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">{{ renameDialog.kind === 'file' ? 'Workbook' : 'Chat Session' }}</p>
          <h3 id="rename-dialog-title">Rename</h3>
        </div>
        <button type="button" class="dialog-icon-button" aria-label="Close" @click="emit('cancel')">
          <AppIcon name="close" />
        </button>
      </div>
      <label class="dialog-field">
        <span>Name</span>
        <input
          :value="renameDraft"
          type="text"
          autocomplete="off"
          autofocus
          @input="handleRenameInput"
        />
      </label>
      <p v-if="errorMessage" class="dialog-error">{{ errorMessage }}</p>
      <div class="dialog-actions">
        <button type="button" class="dialog-secondary" @click="emit('cancel')">Cancel</button>
        <button type="submit" class="dialog-primary" :disabled="isBusy">Save</button>
      </div>
    </form>
  </section>

  <section
    v-if="confirmDialog"
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="confirm-dialog-title"
    @click.self="emit('cancel')"
    @keydown.esc="emit('cancel')"
  >
    <div class="app-dialog">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">{{ confirmDialog.kind === 'file' ? 'Workbook' : 'Chat Session' }}</p>
          <h3 id="confirm-dialog-title">Delete</h3>
        </div>
        <button type="button" class="dialog-icon-button" aria-label="Close" @click="emit('cancel')">
          <AppIcon name="close" />
        </button>
      </div>
      <p class="dialog-copy">
        {{
          confirmDialog.kind === 'file'
            ? `Delete "${confirmDialog.file.display_name}" from file management? Active chats keep their existing context.`
            : `Delete "${confirmDialog.session.title}"?`
        }}
      </p>
      <p v-if="errorMessage" class="dialog-error">{{ errorMessage }}</p>
      <div class="dialog-actions">
        <button type="button" class="dialog-secondary" @click="emit('cancel')">Cancel</button>
        <button
          type="button"
          class="dialog-danger"
          autofocus
          :disabled="isBusy"
          @click="emit('confirmDelete')"
        >
          Delete
        </button>
      </div>
    </div>
  </section>
</template>
