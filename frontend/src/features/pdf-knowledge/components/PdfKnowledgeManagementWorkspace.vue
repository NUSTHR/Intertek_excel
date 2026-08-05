<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceLayout from '../../../components/file-workspace/FileWorkspaceLayout.vue'
import { fileLibraryCopy } from '../../file-library/domain-presentation'
import { usePdfDocumentInsight } from '../composables/use-pdf-document-insight'
import { usePdfKnowledgeLibrary } from '../composables/use-pdf-knowledge-library'
import type { PdfManagedFile, PdfManagementFocusTarget } from '../types'
import PdfManagementFilePane from './PdfManagementFilePane.vue'
import PdfManagementInsightPane from './PdfManagementInsightPane.vue'

const emit = defineEmits<{
  libraryChanged: []
  notificationsRequested: []
}>()

const props = defineProps<{
  focusTarget?: PdfManagementFocusTarget
  active: boolean
  isAdmin: boolean
}>()

const library = usePdfKnowledgeLibrary({
  onLibraryChanged: () => emit('libraryChanged'),
})
const insight = usePdfDocumentInsight(library.selectedFile, library.selectedFiles)
const fileInput = ref<HTMLInputElement | null>(null)
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

watch(
  () => props.active,
  (active) => {
    if (!active) {
      closeDeleteDialog()
    }
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
  <FileWorkspaceLayout
    class="pdfmgmt"
    domain="pdf"
    :title="fileLibraryCopy.pdf.workspaceTitle"
    :search-label="fileLibraryCopy.pdf.searchLabel"
    :search-placeholder="fileLibraryCopy.pdf.searchPlaceholder"
    :is-admin="isAdmin"
    :search-term="library.searchTerm.value"
    @search-term-change="library.setSearchTerm"
  >
    <template #actions>
      <button
        type="button"
        class="topbar-icon-button"
        aria-label="Refresh files"
        :disabled="library.isLoading.value || library.isUploading.value"
        @click="library.loadLibrary"
      >
        <AppIcon name="refresh" />
      </button>
      <button
        type="button"
        class="topbar-icon-button"
        aria-label="Notifications"
        @click="emit('notificationsRequested')"
      >
        <AppIcon name="notifications" />
      </button>
    </template>

    <template #source>
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
          :search-term="library.searchTerm.value"
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
    </template>

    <template #insight>
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
    </template>

    <template #overlay>
      <input
        ref="fileInput"
        class="pdfmgmt-file-input"
        type="file"
        accept=".pdf,application/pdf"
        :aria-label="fileLibraryCopy.pdf.uploadTitle"
        multiple
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
    </template>
  </FileWorkspaceLayout>
</template>
