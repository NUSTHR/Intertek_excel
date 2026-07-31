<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { pdfManagementNavItems } from '../constants'
import { usePdfDocumentInsight } from '../composables/use-pdf-document-insight'
import { usePdfKnowledgeLibrary } from '../composables/use-pdf-knowledge-library'
import type {
  PdfManagedFile,
  PdfManagementFocusTarget,
  PdfWorkspaceMode,
} from '../types'
import PdfManagementFilePane from './PdfManagementFilePane.vue'
import PdfManagementInsightPane from './PdfManagementInsightPane.vue'
import PdfManagementSidebar from './PdfManagementSidebar.vue'
import PdfManagementTopbar from './PdfManagementTopbar.vue'

const emit = defineEmits<{
  changeMode: [mode: PdfWorkspaceMode]
  libraryChanged: []
  openDiagnostics: []
  logout: []
}>()

const props = defineProps<{
  focusTarget?: PdfManagementFocusTarget
  isAdmin: boolean
  userEmail: string
  userRoleLabel: string
}>()

const library = usePdfKnowledgeLibrary({
  onLibraryChanged: () => emit('libraryChanged'),
})
const insight = usePdfDocumentInsight(library.selectedFile, library.selectedFiles)
const fileInput = ref<HTMLInputElement | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const pendingDeleteFile = ref<PdfManagedFile | null>(null)
const isDeletePending = ref(false)
const deleteErrorMessage = ref('')

const pendingDeleteDescendantCount = computed(() => {
  const pending = pendingDeleteFile.value
  if (!pending || pending.kind !== 'folder') {
    return 0
  }
  const lookup = new Map(library.files.value.map((file) => [file.id, file]))
  return library.files.value.filter((file) => {
    let parentId = file.parentId
    const visited = new Set<string>()
    while (parentId && !visited.has(parentId)) {
      if (parentId === pending.id) {
        return true
      }
      visited.add(parentId)
      parentId = lookup.get(parentId)?.parentId
    }
    return false
  }).length
})

onMounted(async () => {
  await library.loadLibrary()
  applyFocusTarget()
  document.addEventListener('keydown', handleDocumentKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDocumentKeyDown)
})

watch(
  () => props.focusTarget?.requestId,
  () => {
    applyFocusTarget()
  },
)

function applyFocusTarget(): void {
  const fileId = props.focusTarget?.fileId
  if (!fileId) {
    return
  }
  if (!library.focusFileById(fileId)) {
    library.errorMessage.value = 'The referenced PDF is no longer available.'
  }
}

function openFolderPicker(): void {
  if (!props.isAdmin || library.isUploading.value) {
    return
  }
  folderInput.value?.click()
}

function openFilePicker(): void {
  if (!props.isAdmin || library.isUploading.value) {
    return
  }
  fileInput.value?.click()
}

function handleUploadInputChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  void library.uploadFiles(files)
  input.value = ''
}

function handleRenameFile(file: PdfManagedFile): void {
  if (!props.isAdmin) {
    return
  }
  const nextName = window.prompt('Rename PDF source', file.name)
  if (nextName === null) {
    return
  }
  void library.renameFile(file, nextName)
}

function handleDeleteFile(file: PdfManagedFile): void {
  if (!props.isAdmin) {
    return
  }
  pendingDeleteFile.value = file
  deleteErrorMessage.value = ''
}

function closeDeleteDialog(): void {
  if (isDeletePending.value) {
    return
  }
  pendingDeleteFile.value = null
  deleteErrorMessage.value = ''
}

async function confirmDeleteFile(): Promise<void> {
  const file = pendingDeleteFile.value
  if (!file || isDeletePending.value) {
    return
  }
  isDeletePending.value = true
  deleteErrorMessage.value = ''
  const deleted = await library.deleteFile(file, true)
  isDeletePending.value = false
  if (deleted) {
    pendingDeleteFile.value = null
  } else {
    deleteErrorMessage.value = library.errorMessage.value
  }
}

function handleDocumentKeyDown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    closeDeleteDialog()
  }
}
</script>

<template>
  <section class="pdfmgmt">
    <PdfManagementSidebar
      :is-admin="isAdmin"
      :nav-items="pdfManagementNavItems"
      :is-uploading="library.isUploading.value"
      :user-email="userEmail"
      :user-role-label="userRoleLabel"
      @change-mode="emit('changeMode', $event)"
      @open-diagnostics="isAdmin && emit('openDiagnostics')"
      @request-upload="openFolderPicker"
      @logout="emit('logout')"
    />

    <PdfManagementTopbar
      :search-term="library.searchTerm.value"
      :is-admin="isAdmin"
      @search-term-change="library.setSearchTerm"
    />

    <main class="pdfmgmt-main">
      <PdfManagementFilePane
        :is-admin="isAdmin"
        :files="library.paginatedFiles.value"
        :directory-files="library.files.value"
        :selected-file-id="library.selectedFileId.value"
        :selected-file-ids="library.selectedFileIds.value"
        :selected-scope-id="library.selectedScopeId.value"
        :scope-breadcrumbs="library.scopeBreadcrumbs.value"
        :total-file-count="library.filteredFiles.value.length"
        :current-page="library.normalizedFilePage.value"
        :page-count="library.filePageCount.value"
        :visible-pages="library.visibleFilePages.value"
        :is-uploading="library.isUploading.value"
        :is-loading="library.isLoading.value"
        :error-message="library.errorMessage.value"
        @select-file="library.selectFile"
        @select-scope="library.selectScope"
        @open-scope="library.openScope"
        @request-upload="openFilePicker"
        @rename-file="handleRenameFile"
        @toggle-visibility="library.toggleFileVisibility"
        @delete-file="handleDeleteFile"
        @page-change="library.setFilePage"
        @page-step="library.stepFilePage"
      />
      <PdfManagementInsightPane
        :is-admin="isAdmin"
        :active-tab="insight.activeTab.value"
        :context-tags="insight.contextTags.value"
        :model-settings="insight.modelSettings.value"
        :model-setting-errors="insight.modelSettingErrors.value"
        :selected-file="library.selectedFile.value"
        :selected-files="library.selectedFiles.value"
        :summary="insight.summary.value"
        :summary-tasks="insight.summaryTasks.value"
        :preview-blocks="insight.previewBlocks.value"
        :schema="insight.schema.value"
        :is-detail-loading="insight.isDetailLoading.value"
        :is-summary-generating="insight.isSummaryGenerating.value"
        :error-message="insight.errorMessage.value"
        @tab-change="insight.setActiveTab"
        @generate-summary="insight.generateSummary"
        @cancel-summary-task="insight.cancelSummaryTask"
        @retry-summary-task="insight.retrySummaryTask"
        @model-setting-change="insight.updateModelPreference"
      />
    </main>

    <button
      type="button"
      class="pdfmgmt-chat-fab"
      aria-label="Open PDF chat"
      @click="emit('changeMode', 'chat')"
    >
      <AppIcon name="chat_bubble" />
    </button>
    <input
      ref="fileInput"
      class="pdfmgmt-file-input"
      type="file"
      accept=".pdf,application/pdf"
      aria-label="Choose PDF files"
      multiple
      @change="handleUploadInputChange"
    />
    <input
      ref="folderInput"
      class="pdfmgmt-file-input"
      type="file"
      multiple
      webkitdirectory
      aria-label="Choose a folder containing PDF files"
      @change="handleUploadInputChange"
    />

    <section
      v-if="pendingDeleteFile"
      class="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pdf-delete-dialog-title"
      @click.self="closeDeleteDialog"
    >
      <div class="app-dialog">
        <div class="dialog-heading">
          <div>
            <p class="eyebrow">
              {{ pendingDeleteFile.kind === 'folder' ? 'PDF Folder' : 'PDF Source' }}
            </p>
            <h3 id="pdf-delete-dialog-title">Delete</h3>
          </div>
          <button
            type="button"
            class="dialog-icon-button"
            aria-label="Close"
            :disabled="isDeletePending"
            @click="closeDeleteDialog"
          >
            <AppIcon name="close" />
          </button>
        </div>
        <p class="dialog-copy">
          Delete "{{ pendingDeleteFile.name }}" from the PDF knowledge directory?
          <template v-if="pendingDeleteDescendantCount > 0">
            This also permanently removes {{ pendingDeleteDescendantCount }}
            nested item{{ pendingDeleteDescendantCount === 1 ? '' : 's' }} and their indexed data.
          </template>
        </p>
        <p v-if="deleteErrorMessage" class="dialog-error">{{ deleteErrorMessage }}</p>
        <div class="dialog-actions">
          <button
            type="button"
            class="dialog-secondary"
            :disabled="isDeletePending"
            @click="closeDeleteDialog"
          >
            Cancel
          </button>
          <button
            type="button"
            class="dialog-danger"
            :disabled="isDeletePending"
            @click="confirmDeleteFile"
          >
            {{ isDeletePending ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </section>
  </section>
</template>
