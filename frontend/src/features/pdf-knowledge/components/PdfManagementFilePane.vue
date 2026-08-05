<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceSourcePane from '../../../components/file-workspace/FileWorkspaceSourcePane.vue'
import {
  fileLibraryCopy,
  formatFileLibraryCount,
  formatFileMetadata,
  formatPdfUploadDescription,
  getFileLibraryEmptyState,
} from '../../file-library/domain-presentation'
import type {
  PdfBreadcrumbItem,
  PdfManagedFile,
  PdfManagedFileKind,
  PdfManagedFileStatus,
} from '../types'
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
  errorMessage: string
  searchTerm: string
}>()

const emit = defineEmits<{
  selectFile: [file: PdfManagedFile]
  selectScope: [scopeId: string]
  openScope: [scopeId: string]
  requestUpload: []
  renameFile: [file: PdfManagedFile]
  toggleVisibility: [file: PdfManagedFile]
  deleteFile: [file: PdfManagedFile]
  pageChange: [page: number]
  pageStep: [direction: -1 | 1]
}>()

const isDirectoryTreeOpen = ref(false)
const openActionMenuId = ref('')
const directoryOverlay = ref<HTMLElement | null>(null)
const directoryTrigger = ref<HTMLButtonElement | null>(null)
const copy = fileLibraryCopy.pdf
const hasSearchQuery = computed(() => props.searchTerm.trim().length > 0)
const countLabel = computed(() => formatFileLibraryCount('pdf', props.totalFileCount))
const emptyState = computed(() => getFileLibraryEmptyState('pdf', hasSearchQuery.value))
const uploadDescription = computed(() => formatPdfUploadDescription(
  props.scopeBreadcrumbs.at(-1)?.label ?? 'Knowledge Base',
  '50 MB',
))

function iconForFileKind(kind: PdfManagedFileKind): string {
  if (kind === 'folder') {
    return 'folder'
  }
  if (kind === 'csv') {
    return 'table_chart'
  }
  if (kind === 'xlsx') {
    return 'table_rows'
  }
  return 'picture_as_pdf'
}

function statusLabel(status: PdfManagedFileStatus): string {
  if (status === 'indexed') {
    return 'Indexed'
  }
  if (status === 'parsing') {
    return 'Parsing'
  }
  if (status === 'uploading') {
    return 'Uploading'
  }
  if (status === 'indexing') {
    return 'Indexing'
  }
  if (status === 'partial') {
    return 'Partial'
  }
  if (status === 'queued') {
    return 'Queued'
  }
  if (status === 'failed') {
    return 'Failed'
  }
  if (status === 'cancelled') {
    return 'Cancelled'
  }
  return 'Ready'
}

function qualityLabel(file: PdfManagedFile): string {
  if (!file.qualityStatus) {
    return ''
  }
  if (file.qualityStatus === 'good') {
    return 'Good'
  }
  if (file.qualityStatus === 'warning') {
    return 'Warning'
  }
  if (file.qualityStatus === 'partial') {
    return 'Partial'
  }
  if (file.qualityStatus === 'failed') {
    return 'Failed'
  }
  return 'Unknown'
}

function qualitySummary(file: PdfManagedFile): string {
  const label = qualityLabel(file)
  if (!label) {
    return ''
  }
  const details: string[] = []
  if (typeof file.coverageRatio === 'number') {
    details.push(`${Math.round(file.coverageRatio * 100)}%`)
  }
  if (file.failedPageCount) {
    details.push(`${file.failedPageCount} failed`)
  } else if (file.warningCount) {
    details.push(`${file.warningCount} warning${file.warningCount > 1 ? 's' : ''}`)
  }
  return details.length ? `${label} / ${details.join(' / ')}` : label
}

function progressForFile(file: PdfManagedFile): number {
  return file.progress ?? (file.status === 'parsing' || file.status === 'indexing' ? 48 : 100)
}

function isFileRowSelected(file: PdfManagedFile): boolean {
  return props.selectedFileIds.has(file.id)
}

function fileMetaLabel(file: PdfManagedFile): string {
  const details = [file.sizeLabel, file.modifiedLabel].filter(Boolean)
  if (details.length > 1) {
    details[1] = `Updated ${details[1]}`
  }
  if (file.status !== 'ready' && file.status !== 'indexed') {
    details.push(statusLabel(file.status))
  }
  const quality = qualitySummary(file)
  if (quality) {
    details.push(quality)
  }
  return formatFileMetadata(details)
}

function openDirectoryTree(): void {
  isDirectoryTreeOpen.value = true
  void nextTick(() => {
    focusFirstDirectoryControl()
  })
}

function closeDirectoryTree(restoreFocus = true): void {
  isDirectoryTreeOpen.value = false
  if (restoreFocus) {
    void nextTick(() => directoryTrigger.value?.focus())
  }
}

function handleDirectoryScopeSelect(scopeId: string): void {
  emit('selectScope', scopeId)
  closeDirectoryTree()
}

function handleDirectoryFileSelect(file: PdfManagedFile): void {
  emit('selectFile', file)
  closeDirectoryTree()
}

function toggleActionMenu(fileId: string): void {
  openActionMenuId.value = openActionMenuId.value === fileId ? '' : fileId
}

function closeActionMenu(): void {
  openActionMenuId.value = ''
}

function renameFromMenu(file: PdfManagedFile): void {
  closeActionMenu()
  emit('renameFile', file)
}

function toggleVisibilityFromMenu(file: PdfManagedFile): void {
  closeActionMenu()
  emit('toggleVisibility', file)
}

function deleteFromMenu(file: PdfManagedFile): void {
  closeActionMenu()
  emit('deleteFile', file)
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (isDirectoryTreeOpen.value) {
    const target = event.target
    if (
      target instanceof Node &&
      !directoryOverlay.value?.contains(target) &&
      !directoryTrigger.value?.contains(target)
    ) {
      closeDirectoryTree(false)
    }
  }
  if (!openActionMenuId.value) {
    return
  }
  const target = event.target
  if (
    target instanceof Element &&
    target.closest('.item-action-menu, .menu-trigger')
  ) {
    return
  }
  closeActionMenu()
}

function handleDocumentKeyDown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    if (isDirectoryTreeOpen.value) {
      event.preventDefault()
      closeDirectoryTree()
      return
    }
    closeActionMenu()
    return
  }
  if (event.key === 'Tab' && isDirectoryTreeOpen.value) {
    trapDirectoryFocus(event)
  }
}

function focusableDirectoryControls(): HTMLElement[] {
  if (!directoryOverlay.value) {
    return []
  }
  return Array.from(
    directoryOverlay.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  )
}

function focusFirstDirectoryControl(): void {
  focusableDirectoryControls()[0]?.focus()
}

function trapDirectoryFocus(event: KeyboardEvent): void {
  const controls = focusableDirectoryControls()
  if (controls.length === 0) {
    event.preventDefault()
    directoryOverlay.value?.focus()
    return
  }
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
        aria-label="Directory Tree"
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
          @select-scope="handleDirectoryScopeSelect"
          @select-file="handleDirectoryFileSelect"
        />
        <footer class="pdfmgmt-directory-overlay-footer">
          <span>Quick Actions</span>
          <button type="button" disabled>
            <AppIcon name="create_new_folder" />
            <span>New Folder</span>
          </button>
        </footer>
      </div>
    </template>

    <template #header>
      <div class="pdfmgmt-breadcrumb-row panel-heading">
        <div class="pdfmgmt-breadcrumb-group">
          <nav aria-label="Knowledge path">
            <template v-for="(crumb, index) in scopeBreadcrumbs" :key="`${crumb}-${index}`">
              <button
                type="button"
                class="pdfmgmt-breadcrumb-button"
                :class="{ active: crumb.active }"
                :aria-current="crumb.active ? 'page' : undefined"
                @click="emit('openScope', crumb.id)"
              >
                {{ crumb.label }}
              </button>
              <AppIcon
                v-if="index < scopeBreadcrumbs.length - 1"
                name="chevron_right"
                class="pdfmgmt-breadcrumb-separator"
              />
            </template>
          </nav>
          <button
            ref="directoryTrigger"
            type="button"
            class="pdfmgmt-directory-trigger"
            aria-label="View directory tree"
            @click="openDirectoryTree"
          >
            <AppIcon name="account_tree" />
          </button>
        </div>
        <span class="pdfmgmt-count-pill">{{ countLabel }}</span>
      </div>
    </template>

    <template #upload>
      <button
        v-if="isAdmin"
        type="button"
        class="pdfmgmt-dropzone file-upload-zone"
        :disabled="isUploading"
        @click="emit('requestUpload')"
      >
        <span class="pdfmgmt-dropzone-icon file-upload-icon">
          <AppIcon name="upload_file" />
        </span>
        <span>
          <strong>{{ isUploading ? copy.uploadPendingTitle : copy.uploadTitle }}</strong>
          <small>{{ uploadDescription }}</small>
        </span>
      </button>
    </template>

    <template #status>
      <p v-if="errorMessage" class="pdfmgmt-inline-error">{{ errorMessage }}</p>
    </template>

    <template #list>
      <div class="pdfmgmt-file-table" role="list" aria-label="Knowledge files">
        <div v-if="files.length > 0" class="pdfmgmt-file-header" aria-hidden="true">
          <span>Type</span>
          <span>Name</span>
          <span>Size</span>
          <span>Status</span>
          <span></span>
        </div>

        <div v-if="isLoading" class="pdfmgmt-file-empty">
          <AppIcon name="refresh" />
          <strong>Loading knowledge files</strong>
        </div>

        <div v-else-if="files.length === 0" class="pdfmgmt-file-empty">
          <AppIcon name="folder_open" />
          <strong>{{ emptyState.title }}</strong>
          <span>{{ emptyState.detail }}</span>
        </div>

        <article
          v-else
          v-for="file in files"
          :key="file.id"
          class="pdfmgmt-file-row"
          :class="[
            'file-library-card',
            {
              selected: isFileRowSelected(file),
              active: isFileRowSelected(file),
              parsing: file.status === 'parsing' || file.status === 'indexing',
              'menu-open': openActionMenuId === file.id,
            },
          ]"
          role="listitem"
        >
          <input
            class="pdfmgmt-file-check"
            type="checkbox"
            :checked="isFileRowSelected(file)"
            :aria-label="`Select ${file.name}`"
            @click.stop="emit('selectFile', file)"
            @change.prevent
          />
          <button
            type="button"
            class="pdfmgmt-file-row-hitbox"
            :aria-label="`Select ${file.name}`"
            @click="emit('selectFile', file)"
          ></button>
          <button
            type="button"
            class="pdfmgmt-file-main"
            @click="emit('selectFile', file)"
          >
            <span class="pdfmgmt-file-icon file-badge large" :class="file.kind">
              <AppIcon :name="iconForFileKind(file.kind)" />
            </span>
            <span class="pdfmgmt-file-name file-card-main">
              <strong>{{ file.name }}</strong>
              <small class="file-meta-line">{{ fileMetaLabel(file) }}</small>
            </span>
            <span
              v-if="['uploading', 'queued', 'parsing', 'indexing'].includes(file.status)"
              class="pdfmgmt-progress-track"
            >
              <span
                class="pdfmgmt-progress-fill"
                :style="{ width: `${progressForFile(file)}%` }"
              ></span>
            </span>
          </button>
          <div v-if="isAdmin" class="pdfmgmt-row-menu file-card-actions" @click.stop>
            <button
              type="button"
              class="pdfmgmt-row-menu-trigger menu-trigger"
              :class="{ active: openActionMenuId === file.id }"
              :aria-label="`Actions for ${file.name}`"
              :aria-expanded="openActionMenuId === file.id"
              @click="toggleActionMenu(file.id)"
            >
              <AppIcon name="more_vert" />
            </button>
            <div
              v-if="openActionMenuId === file.id"
              class="pdfmgmt-row-menu-popover item-action-menu file-card-menu"
            >
              <button type="button" @click="renameFromMenu(file)">
                <AppIcon name="edit" />
                <span>Rename</span>
              </button>
              <button type="button" @click="toggleVisibilityFromMenu(file)">
                <AppIcon :name="file.visibleToMembers ? 'visibility_off' : 'visibility'" />
                <span>
                  {{ file.visibleToMembers ? 'Hide from members' : 'Show to members' }}
                </span>
              </button>
              <button type="button" class="danger" @click="deleteFromMenu(file)">
                <AppIcon name="delete" />
                <span>Delete</span>
              </button>
            </div>
          </div>
          <button
            v-if="file.kind === 'folder'"
            type="button"
            class="pdfmgmt-folder-open"
            :aria-label="`Open folder ${file.name}`"
            title="Open folder"
            @click.stop="emit('openScope', file.id)"
          >
            <AppIcon name="chevron_right" />
          </button>
        </article>
      </div>
    </template>

    <template #pagination>
      <div class="pdfmgmt-pagination file-pagination">
        <button
          type="button"
          class="pagination-link"
          :disabled="currentPage <= 1"
          @click="emit('pageStep', -1)"
        >
          <AppIcon name="chevron_left" />
          Previous
        </button>
        <div class="pagination-pages">
          <button
            v-for="page in visiblePages"
            :key="page"
            type="button"
            :class="{ active: page === currentPage }"
            @click="emit('pageChange', page)"
          >
            {{ page }}
          </button>
        </div>
        <button
          type="button"
          class="pagination-link"
          :disabled="currentPage >= pageCount"
          @click="emit('pageStep', 1)"
        >
          Next
          <AppIcon name="chevron_right" />
        </button>
      </div>
    </template>
  </FileWorkspaceSourcePane>
</template>
