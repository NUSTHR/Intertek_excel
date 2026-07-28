<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { pdfManagementNavItems } from '../constants'
import { usePdfDocumentInsight } from '../composables/use-pdf-document-insight'
import { usePdfKnowledgeLibrary } from '../composables/use-pdf-knowledge-library'
import type { PdfManagedFile, PdfWorkspaceMode } from '../types'
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
  isAdmin: boolean
  userEmail: string
  userRoleLabel: string
}>()

const library = usePdfKnowledgeLibrary({
  onLibraryChanged: () => emit('libraryChanged'),
})
const insight = usePdfDocumentInsight(library.selectedFile, library.selectedFiles)
const folderInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  void library.loadLibrary()
})

function openFolderPicker(): void {
  if (!props.isAdmin || library.isUploading.value) {
    return
  }
  folderInput.value?.click()
}

function handleFolderInputChange(event: Event): void {
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
  if (!window.confirm(`Delete ${file.name} from the PDF knowledge directory?`)) {
    return
  }
  void library.deleteFile(file)
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
      @open-diagnostics="emit('openDiagnostics')"
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
        @request-upload="openFolderPicker"
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
      ref="folderInput"
      class="pdfmgmt-file-input"
      type="file"
      multiple
      webkitdirectory
      @change="handleFolderInputChange"
    />
  </section>
</template>
