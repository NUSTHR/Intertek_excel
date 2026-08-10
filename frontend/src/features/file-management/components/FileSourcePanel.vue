<script setup lang="ts">
import { computed } from 'vue'

import FileWorkspaceSourcePane from '../../../components/file-workspace/FileWorkspaceSourcePane.vue'
import { fileIcon, fileTypeLabel, formatDate } from '../../../app/workspace-utils'
import {
  fileLibraryCopy,
  formatFileLibraryCount,
  getFileLibraryEmptyState,
} from '../../file-library/domain-presentation'
import BaseFileDropzone from '../../../shared/file-workspace/components/BaseFileDropzone.vue'
import BaseFileLibraryHeading from '../../../shared/file-workspace/components/BaseFileLibraryHeading.vue'
import BaseFilePagination from '../../../shared/file-workspace/components/BaseFilePagination.vue'
import BaseFileRow from '../../../shared/file-workspace/components/BaseFileRow.vue'
import BaseFileState from '../../../shared/file-workspace/components/BaseFileState.vue'
import { buildFilePaginationViewModel } from '../../../shared/file-workspace/composables/use-pagination-label'
import type {
  BaseFileRowViewModel,
  FileActionId,
  FileWorkspaceIconName,
} from '../../../shared/file-workspace/file-card-contract'
import type { FileActionItem } from '../../../shared/file-workspace/file-action-menu-contract'
import { fileWorkspaceCopy } from '../../../shared/file-workspace/copy'
import type { ExcelFile } from '../../../types/excel-assets'

const props = defineProps<{
  files: ExcelFile[]
  totalFileCount: number
  selectedFileId: string
  openMenuFileId: string
  pinnedFileIds: string[]
  disabled: boolean
  searchTerm: string
  uploadAccept: string
  uploadHelpText: string
  uploadMaxBytes: number
  currentPage: number
  pageCount: number
  visiblePages: number[]
  paginationLabel: string
}>()

const emit = defineEmits<{
  uploadSelected: [file: File | null]
  uploadValidationError: [message: string]
  selectFile: [file: ExcelFile]
  toggleMenu: [fileId: string]
  togglePin: [file: ExcelFile]
  renameFile: [file: ExcelFile]
  toggleVisibility: [file: ExcelFile]
  deleteFile: [file: ExcelFile]
  setPage: [page: number]
  stepPage: [direction: 1 | -1]
}>()

const copy = fileLibraryCopy.excel
const hasSearchQuery = computed(() => props.searchTerm.trim().length > 0)
const countLabel = computed(() => formatFileLibraryCount('excel', props.totalFileCount))
const emptyState = computed(() => getFileLibraryEmptyState('excel', hasSearchQuery.value))
const paginationModel = computed(() => buildFilePaginationViewModel({
  totalCount: props.totalFileCount,
  currentPage: props.currentPage,
}))

function isFilePinned(fileId: string): boolean {
  return props.pinnedFileIds.includes(fileId)
}

function rowModel(file: ExcelFile): BaseFileRowViewModel {
  return {
    id: file.file_id,
    domain: 'excel',
    kind: 'file',
    displayName: file.display_name,
    metaParts: [fileTypeLabel(file), `Updated ${formatDate(file.updated_at)}`],
    iconName: fileIcon(file) as FileWorkspaceIconName,
    isSelected: file.file_id === props.selectedFileId,
    isPinned: isFilePinned(file.file_id),
    isMultiSelectable: false,
    isChecked: false,
    isProgressing: false,
    progressPercent: 100,
    isFolderOpenable: false,
    visibilityChip: file.visible_to_members ? undefined : 'Admin only',
  }
}

function rowActions(file: ExcelFile): FileActionItem[] {
  return [
    {
      id: isFilePinned(file.file_id) ? 'unpin' : 'pin',
      label: isFilePinned(file.file_id) ? 'Unpin' : 'Pin',
      iconName: 'push_pin',
    },
    { id: 'rename', label: fileWorkspaceCopy.actions.rename, iconName: 'edit' },
    {
      id: file.visible_to_members ? 'hide' : 'show',
      label: file.visible_to_members
        ? fileWorkspaceCopy.actions.hide
        : fileWorkspaceCopy.actions.show,
      iconName: file.visible_to_members ? 'visibility_off' : 'visibility',
    },
    { id: 'delete', label: fileWorkspaceCopy.actions.delete, iconName: 'delete', tone: 'danger' },
  ]
}

function fileById(id: string): ExcelFile | undefined {
  return props.files.find((file) => file.file_id === id)
}

function handleAction(model: BaseFileRowViewModel, action: FileActionId): void {
  const file = fileById(model.id)
  if (!file) {
    return
  }
  if (action === 'pin' || action === 'unpin') {
    emit('togglePin', file)
  } else if (action === 'rename') {
    emit('renameFile', file)
  } else if (action === 'hide' || action === 'show') {
    emit('toggleVisibility', file)
  } else if (action === 'delete') {
    emit('deleteFile', file)
  }
}
</script>

<template>
  <FileWorkspaceSourcePane domain="excel">
    <template #header>
      <BaseFileLibraryHeading :title="copy.listTitle" :count-label="countLabel" />
    </template>

    <template #upload>
      <BaseFileDropzone
        domain="excel"
        :accept="uploadAccept"
        :multiple="false"
        :help-text="uploadHelpText"
        :is-disabled="disabled"
        :max-size-bytes="uploadMaxBytes"
        :prompt-label="copy.uploadTitle"
        @files-selected="emit('uploadSelected', $event[0]?.file ?? null)"
        @validation-error="emit('uploadValidationError', $event)"
      />
    </template>

    <template #list>
      <div class="file-workspace-base-list" role="list" aria-label="Excel workbooks">
        <BaseFileState
          v-if="totalFileCount === 0"
          domain="excel"
          :icon-name="hasSearchQuery ? 'search' : 'folder_open'"
          :title="emptyState.title"
          :detail="emptyState.detail"
        />
        <BaseFileRow
          v-for="file in files"
          v-else
          :key="file.file_id"
          :model="rowModel(file)"
          :actions="rowActions(file)"
          :menu-open="openMenuFileId === file.file_id"
          :disabled="disabled"
          @select="emit('selectFile', file)"
          @toggle-menu="emit('toggleMenu', file.file_id)"
          @close-menu="emit('toggleMenu', '')"
          @request-action="handleAction"
        />
      </div>
    </template>

    <template #pagination>
      <BaseFilePagination
        :model="paginationModel"
        @set-page="emit('setPage', $event)"
        @step-page="emit('stepPage', $event)"
      />
    </template>
  </FileWorkspaceSourcePane>
</template>
