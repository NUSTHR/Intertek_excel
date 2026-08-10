<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceSourcePane from '../../../components/file-workspace/FileWorkspaceSourcePane.vue'
import {
  fileLibraryCopy,
  formatFileLibraryCount,
  formatPdfUploadDescription,
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
import type {
  PdfBreadcrumbItem,
  PdfManagedFile,
  PdfManagedFileKind,
  PdfManagedFileStatus,
} from '../types'
import type { FileUploadSelection } from '../../../types/file-upload'
import PdfManagementDirectoryTree from './PdfManagementDirectoryTree.vue'

const props = defineProps<{
  isAdmin: boolean
  files: PdfManagedFile[]
  directoryFiles: PdfManagedFile[]
  selectedFileId: string
  selectedFileIds: Set<string>
  selectedScopeId: string
  scopeBreadcrumbs: PdfBreadcrumbItem[]
  totalFileCount: number
  currentPage: number
  pageCount: number
  visiblePages: number[]
  isUploading: boolean
  isLoading: boolean
  loadErrorMessage: string
  errorMessage: string
  searchTerm: string
}>()

const emit = defineEmits<{
  selectFile: [file: PdfManagedFile]
  selectScope: [scopeId: string]
  openScope: [scopeId: string]
  uploadFiles: [selections: FileUploadSelection[]]
  uploadValidationError: [message: string]
  renameFile: [file: PdfManagedFile]
  toggleVisibility: [file: PdfManagedFile]
  deleteFile: [file: PdfManagedFile]
  pageChange: [page: number]
  pageStep: [direction: -1 | 1]
}>()

const pdfMaxUploadBytes = 50 * 1024 * 1024
const isDirectoryTreeOpen = ref(false)
const openActionMenuId = ref('')
const directoryOverlay = ref<HTMLElement | null>(null)
const directoryTrigger = ref<HTMLButtonElement | null>(null)
const copy = fileLibraryCopy.pdf
const hasSearchQuery = computed(() => props.searchTerm.trim().length > 0)
const countLabel = computed(() => formatFileLibraryCount('pdf', props.totalFileCount))
const emptyState = computed(() => getFileLibraryEmptyState('pdf', hasSearchQuery.value))
const uploadDescription = computed(() => formatPdfUploadDescription(
  props.scopeBreadcrumbs.at(-1)?.label ?? copy.listTitle,
  '50 MB',
))
const fatalError = computed(() => !props.isLoading && props.files.length === 0
  ? props.loadErrorMessage
  : '')
const paginationModel = computed(() => buildFilePaginationViewModel({
  totalCount: props.totalFileCount,
  currentPage: props.currentPage,
}))

function iconForFileKind(kind: PdfManagedFileKind): FileWorkspaceIconName {
  if (kind === 'folder') return 'folder'
  if (kind === 'csv') return 'table_chart'
  if (kind === 'xlsx') return 'table_rows'
  return 'picture_as_pdf'
}

function statusLabel(status: PdfManagedFileStatus): string {
  const labels: Record<PdfManagedFileStatus, string> = {
    indexed: 'Indexed',
    ready: 'Ready',
    uploading: 'Uploading',
    queued: 'Queued',
    parsing: 'Parsing',
    indexing: 'Indexing',
    partial: 'Partial',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }
  return labels[status]
}

function qualitySummary(file: PdfManagedFile): string {
  if (!file.qualityStatus) return ''
  const label = file.qualityStatus.charAt(0).toUpperCase() + file.qualityStatus.slice(1)
  if (typeof file.coverageRatio === 'number') return `${label} / ${Math.round(file.coverageRatio * 100)}%`
  if (file.failedPageCount) return `${label} / ${file.failedPageCount} failed`
  if (file.warningCount) return `${label} / ${file.warningCount} warning${file.warningCount === 1 ? '' : 's'}`
  return label
}

function rowModel(file: PdfManagedFile): BaseFileRowViewModel {
  const isProgressing = ['uploading', 'queued', 'parsing', 'indexing'].includes(file.status)
  const metaParts = [file.sizeLabel, file.modifiedLabel ? `Updated ${file.modifiedLabel}` : '']
  if (file.status !== 'ready' && file.status !== 'indexed') metaParts.push(statusLabel(file.status))
  const quality = qualitySummary(file)
  if (quality) metaParts.push(quality)
  return {
    id: file.id,
    domain: 'pdf',
    kind: file.kind === 'folder' ? 'folder' : 'file',
    displayName: file.name,
    metaParts: metaParts.filter(Boolean),
    iconName: iconForFileKind(file.kind),
    isSelected: props.selectedFileIds.has(file.id),
    isPinned: false,
    isMultiSelectable: true,
    isChecked: props.selectedFileIds.has(file.id),
    isProgressing,
    progressPercent: file.progress ?? (isProgressing ? 48 : 100),
    isFolderOpenable: file.kind === 'folder',
    visibilityChip: file.visibleToMembers ? undefined : 'Admin only',
  }
}

function rowActions(file: PdfManagedFile): FileActionItem[] {
  if (!props.isAdmin) return []
  return [
    { id: 'rename', label: fileWorkspaceCopy.actions.rename, iconName: 'edit' },
    {
      id: file.visibleToMembers ? 'hide' : 'show',
      label: file.visibleToMembers
        ? fileWorkspaceCopy.actions.hide
        : fileWorkspaceCopy.actions.show,
      iconName: file.visibleToMembers ? 'visibility_off' : 'visibility',
    },
    { id: 'delete', label: fileWorkspaceCopy.actions.delete, iconName: 'delete', tone: 'danger' },
  ]
}

function fileById(id: string): PdfManagedFile | undefined {
  return props.files.find((file) => file.id === id)
}

function handleAction(model: BaseFileRowViewModel, action: FileActionId): void {
  const file = fileById(model.id)
  if (!file) return
  openActionMenuId.value = ''
  if (action === 'rename') emit('renameFile', file)
  else if (action === 'hide' || action === 'show') emit('toggleVisibility', file)
  else if (action === 'delete') emit('deleteFile', file)
}

function openDirectoryTree(): void {
  isDirectoryTreeOpen.value = true
  void nextTick(() => focusableDirectoryControls()[0]?.focus())
}

function closeDirectoryTree(restoreFocus = true): void {
  isDirectoryTreeOpen.value = false
  if (restoreFocus) void nextTick(() => directoryTrigger.value?.focus())
}

function focusableDirectoryControls(): HTMLElement[] {
  if (!directoryOverlay.value) return []
  return Array.from(directoryOverlay.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])',
  ))
}

function handleDocumentPointerDown(event: PointerEvent): void {
  const target = event.target
  if (
    isDirectoryTreeOpen.value &&
    target instanceof Node &&
    !directoryOverlay.value?.contains(target) &&
    !directoryTrigger.value?.contains(target)
  ) closeDirectoryTree(false)
}

function handleDocumentKeyDown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && isDirectoryTreeOpen.value) {
    event.preventDefault()
    closeDirectoryTree()
    return
  }
  if (event.key !== 'Tab' || !isDirectoryTreeOpen.value) return
  const controls = focusableDirectoryControls()
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeyDown)
})
</script>

<template>
  <FileWorkspaceSourcePane domain="pdf" :overlay-open="isDirectoryTreeOpen">
    <template #overlay>
      <div
        ref="directoryOverlay"
        class="pdfmgmt-directory-overlay"
        :class="{ open: isDirectoryTreeOpen }"
        role="dialog"
        aria-label="Directory tree"
        aria-modal="true"
        :aria-hidden="!isDirectoryTreeOpen"
        :tabindex="isDirectoryTreeOpen ? 0 : -1"
      >
        <header class="pdfmgmt-directory-overlay-header">
          <strong>Directory Tree</strong>
          <button type="button" aria-label="Close directory tree" @click="closeDirectoryTree()">
            <AppIcon name="close" />
          </button>
        </header>
        <PdfManagementDirectoryTree
          :files="directoryFiles"
          :selected-scope-id="selectedScopeId"
          :selected-file-id="selectedFileId"
          @select-scope="emit('selectScope', $event); closeDirectoryTree()"
          @select-file="emit('selectFile', $event); closeDirectoryTree()"
        />
      </div>
    </template>

    <template #header>
      <BaseFileLibraryHeading :title="copy.listTitle" :count-label="countLabel">
        <template #navigation>
          <div class="file-workspace-base-breadcrumb-group">
            <nav v-if="scopeBreadcrumbs.length > 1" aria-label="PDF Files path">
              <template
                v-for="(crumb, index) in scopeBreadcrumbs.slice(1)"
                :key="`${crumb.id}-${index}`"
              >
                <AppIcon name="chevron_right" />
                <button
                  type="button"
                  class="file-workspace-base-breadcrumb"
                  :data-active="crumb.active"
                  :aria-current="crumb.active ? 'page' : undefined"
                  @click="emit('openScope', crumb.id)"
                >{{ crumb.label }}</button>
              </template>
            </nav>
            <button
              ref="directoryTrigger"
              type="button"
              class="file-workspace-base-directory-trigger"
              aria-label="View PDF Files directory tree"
              @click="openDirectoryTree"
            ><AppIcon name="account_tree" /></button>
          </div>
        </template>
      </BaseFileLibraryHeading>
    </template>

    <template #upload>
      <BaseFileDropzone
        v-if="isAdmin"
        domain="pdf"
        accept=".pdf,application/pdf"
        multiple
        allow-directories
        directory-label="Choose folder"
        :help-text="uploadDescription"
        :is-disabled="isUploading"
        :max-size-bytes="pdfMaxUploadBytes"
        :prompt-label="isUploading ? copy.uploadPendingTitle : copy.uploadTitle"
        @files-selected="emit('uploadFiles', $event)"
        @validation-error="emit('uploadValidationError', $event)"
      />
    </template>

    <template #status>
      <p v-if="errorMessage && !fatalError" class="file-workspace-base-inline-error" role="status">
        {{ errorMessage }}
      </p>
    </template>

    <template #list>
      <div class="file-workspace-base-list" role="list" aria-label="PDF files">
        <BaseFileState
          v-if="isLoading && files.length === 0"
          domain="pdf"
          tone="loading"
          icon-name="refresh"
          title="Loading PDF files"
          detail="Refreshing the current knowledge directory."
        />
        <BaseFileState
          v-else-if="fatalError"
          domain="pdf"
          tone="error"
          icon-name="description"
          title="PDF files could not be loaded"
          :detail="fatalError"
        />
        <BaseFileState
          v-else-if="files.length === 0"
          domain="pdf"
          :icon-name="hasSearchQuery ? 'search' : 'folder_open'"
          :title="emptyState.title"
          :detail="emptyState.detail"
        />
        <BaseFileRow
          v-for="file in files"
          v-else
          :key="file.id"
          :model="rowModel(file)"
          :actions="rowActions(file)"
          :menu-open="openActionMenuId === file.id"
          @select="emit('selectFile', file)"
          @toggle-check="emit('selectFile', file)"
          @open-folder="emit('openScope', file.id)"
          @toggle-menu="openActionMenuId = openActionMenuId === file.id ? '' : file.id"
          @close-menu="openActionMenuId = ''"
          @request-action="handleAction"
        />
      </div>
    </template>

    <template #pagination>
      <BaseFilePagination
        :model="paginationModel"
        @set-page="emit('pageChange', $event)"
        @step-page="emit('pageStep', $event)"
      />
    </template>
  </FileWorkspaceSourcePane>
</template>
