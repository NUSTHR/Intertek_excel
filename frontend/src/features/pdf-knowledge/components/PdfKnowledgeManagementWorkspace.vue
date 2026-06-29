<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { pdfManagementNavItems } from '../constants'
import { usePdfDocumentInsight } from '../composables/use-pdf-document-insight'
import { usePdfKnowledgeLibrary } from '../composables/use-pdf-knowledge-library'
import type { PdfWorkspaceMode } from '../types'
import PdfManagementFilePane from './PdfManagementFilePane.vue'
import PdfManagementInsightPane from './PdfManagementInsightPane.vue'
import PdfManagementSidebar from './PdfManagementSidebar.vue'
import PdfManagementTopbar from './PdfManagementTopbar.vue'

const emit = defineEmits<{
  changeMode: [mode: PdfWorkspaceMode]
}>()

const library = usePdfKnowledgeLibrary()
const insight = usePdfDocumentInsight(library.selectedFile)
const folderInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  void library.loadLibrary()
})

function openFolderPicker(): void {
  if (library.isUploading.value) {
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
</script>

<template>
  <section class="pdfmgmt">
    <PdfManagementSidebar
      :nav-items="pdfManagementNavItems"
      :is-uploading="library.isUploading.value"
      @change-mode="emit('changeMode', $event)"
      @request-upload="openFolderPicker"
    />

    <PdfManagementTopbar
      :search-term="library.searchTerm.value"
      @search-term-change="library.setSearchTerm"
    />

    <main class="pdfmgmt-main">
      <PdfManagementFilePane
        :files="library.paginatedFiles.value"
        :selected-file-id="library.selectedFileId.value"
        :total-file-count="library.filteredFiles.value.length"
        :current-page="library.normalizedFilePage.value"
        :page-count="library.filePageCount.value"
        :visible-pages="library.visibleFilePages.value"
        :upload-tasks="library.uploadTasks.value"
        :upload-task-summary="library.uploadTaskSummary.value"
        :is-uploading="library.isUploading.value"
        :is-loading="library.isLoading.value"
        :error-message="library.errorMessage.value"
        @select-file="library.selectFile"
        @request-upload="openFolderPicker"
        @page-change="library.setFilePage"
        @page-step="library.stepFilePage"
      />
      <PdfManagementInsightPane
        :active-tab="insight.activeTab.value"
        :context-tags="insight.contextTags.value"
        :model-settings="insight.modelSettings.value"
        :selected-file="library.selectedFile.value"
        :summary="insight.summary.value"
        :preview-blocks="insight.previewBlocks.value"
        :schema="insight.schema.value"
        :is-detail-loading="insight.isDetailLoading.value"
        :is-summary-generating="insight.isSummaryGenerating.value"
        :error-message="insight.errorMessage.value"
        @tab-change="insight.setActiveTab"
        @generate-summary="insight.generateSummary"
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
