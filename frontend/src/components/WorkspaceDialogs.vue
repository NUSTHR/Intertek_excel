<script setup lang="ts">
import BaseWorkspaceDialog from '../shared/file-workspace/components/BaseWorkspaceDialog.vue'
import type { ConfirmDialog, RenameDialog } from '../app/workspace-types'

const props = defineProps<{
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

function renameKindLabel(): string {
  return props.renameDialog?.kind === 'file' ? 'Excel Workbook' : 'Chat Session'
}

function renameDisplayName(): string {
  const dialog = props.renameDialog
  if (!dialog) return ''
  return dialog.kind === 'file' ? dialog.file.display_name : dialog.session.title
}

function deleteKindLabel(): string {
  return props.confirmDialog?.kind === 'file' ? 'Excel Workbook' : 'Chat Session'
}

function deleteDisplayName(): string {
  const dialog = props.confirmDialog
  if (!dialog) return ''
  return dialog.kind === 'file' ? dialog.file.display_name : dialog.session.title
}

function deleteDescription(): string {
  const dialog = props.confirmDialog
  if (!dialog) return ''
  return dialog.kind === 'file'
    ? `Archive "${dialog.file.display_name}" from file management? The workbook data and historical chat evidence will be retained until a separate permanent purge is requested.`
    : `Delete "${dialog.session.title}"?`
}
</script>

<template>
  <BaseWorkspaceDialog
    :open="Boolean(renameDialog)"
    mode="rename"
    :kind-label="renameKindLabel()"
    :display-name="renameDisplayName()"
    :draft="renameDraft"
    :error-message="errorMessage"
    :is-busy="isBusy"
    @cancel="emit('cancel')"
    @confirm="emit('submitRename')"
    @update-draft="emit('updateRenameDraft', $event)"
  />

  <BaseWorkspaceDialog
    :open="Boolean(confirmDialog)"
    mode="delete"
    :kind-label="deleteKindLabel()"
    :display-name="deleteDisplayName()"
    :description="deleteDescription()"
    :error-message="errorMessage"
    :is-busy="isBusy"
    @cancel="emit('cancel')"
    @confirm="emit('confirmDelete')"
  />
</template>
