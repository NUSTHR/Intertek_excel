<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceLayout from '../../../components/file-workspace/FileWorkspaceLayout.vue'
import BaseWorkspaceDialog from '../../../shared/file-workspace/components/BaseWorkspaceDialog.vue'
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
const pendingDeleteFile = ref<PdfManagedFile | null>(null)
const pendingRenameFile = ref<PdfManagedFile | null>(null)
const renameDraft = ref('')
const isRenamePending = ref(false)
const renameErrorMessage = ref('')
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
      closeRenameDialog()
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

function handleUploadFiles(files: File[]): void {
  void library.uploadFiles(files)
}

function handleUploadValidationError(message: string): void {
  library.errorMessage.value = message
}

function handleRenameFile(file: PdfManagedFile): void {
  if (!props.isAdmin) {
    return
  }
  pendingRenameFile.value = file
  renameDraft.value = file.name
  renameErrorMessage.value = ''
}

function closeRenameDialog(): void {
  if (isRenamePending.value) return
  pendingRenameFile.value = null
  renameDraft.value = ''
  renameErrorMessage.value = ''
}

async function confirmRenameFile(): Promise<void> {
  const file = pendingRenameFile.value
  const nextName = renameDraft.value.trim()
  if (!file || isRenamePending.value) return
  if (!nextName) {
    renameErrorMessage.value = 'Name cannot be empty.'
    return
  }
  if (nextName === file.name) {
    closeRenameDialog()
    return
  }
  isRenamePending.value = true
  renameErrorMessage.value = ''
  await library.renameFile(file, nextName)
  isRenamePending.value = false
  if (library.errorMessage.value) {
    renameErrorMessage.value = library.errorMessage.value
    return
  }
  closeRenameDialog()
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
    closeRenameDialog()
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
          @upload-files="handleUploadFiles"
          @upload-validation-error="handleUploadValidationError"
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
      <BaseWorkspaceDialog
        :open="Boolean(pendingRenameFile)"
        mode="rename"
        kind-label="PDF Source"
        :display-name="pendingRenameFile?.name ?? ''"
        :draft="renameDraft"
        :error-message="renameErrorMessage"
        :is-busy="isRenamePending"
        @cancel="closeRenameDialog"
        @confirm="confirmRenameFile"
        @update-draft="renameDraft = $event"
      />
      <BaseWorkspaceDialog
        :open="Boolean(pendingDeleteFile)"
        mode="delete"
        :kind-label="pendingDeleteFile?.kind === 'folder' ? 'PDF Folder' : 'PDF Source'"
        :display-name="pendingDeleteFile?.name ?? ''"
        :description="pendingDeleteFile
          ? `Delete &quot;${pendingDeleteFile.name}&quot; from the PDF knowledge directory?${pendingDeleteDescendantCount > 0
            ? ` This also permanently removes ${pendingDeleteDescendantCount} nested item${pendingDeleteDescendantCount === 1 ? '' : 's'} and their indexed data.`
            : ''}`
          : ''"
        :error-message="deleteErrorMessage"
        :is-busy="isDeletePending"
        @cancel="closeDeleteDialog"
        @confirm="confirmDeleteFile"
      />
    </template>
  </FileWorkspaceLayout>
</template>
