<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { listPdfKnowledgeFiles } from '../../../api/pdf-knowledge-api'
import { usePdfChat } from '../composables/use-pdf-chat'
import type {
  PdfKnowledgeNode,
  PdfManagedFile,
  PdfRecentChat,
  PdfSidebarView,
  PdfWorkspaceMode,
} from '../types'
import PdfChatWorkspace from './PdfChatWorkspace.vue'
import PdfKnowledgeManagementWorkspace from './PdfKnowledgeManagementWorkspace.vue'
import PdfKnowledgeSidebar from './PdfKnowledgeSidebar.vue'
import PdfSourceCitations from './PdfSourceCitations.vue'

const workspaceMode = ref<PdfWorkspaceMode>('management')
const activeSidebarView = ref<PdfSidebarView>('knowledge')
const isCitationPanelCollapsed = ref(false)
const hasUserToggledCitationPanel = ref(false)
const knowledgeFiles = ref<PdfManagedFile[]>([])
const pdfChat = usePdfChat()

const knowledgeTree = computed<PdfKnowledgeNode[]>(() => {
  return buildKnowledgeTree(knowledgeFiles.value)
})

const recentChats = computed<PdfRecentChat[]>(() => [])

function shouldCollapseCitationsForViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth <= 860
}

function changeSidebarView(view: PdfSidebarView): void {
  activeSidebarView.value = view
}

function startNewChat(): void {
  activeSidebarView.value = 'chats'
  pdfChat.clearChat()
}

function toggleCitationPanel(): void {
  hasUserToggledCitationPanel.value = true
  isCitationPanelCollapsed.value = !isCitationPanelCollapsed.value
}

function changeWorkspaceMode(mode: PdfWorkspaceMode): void {
  workspaceMode.value = mode
  if (mode === 'chat') {
    syncCitationPanelWithViewport()
  }
}

function syncCitationPanelWithViewport(): void {
  if (hasUserToggledCitationPanel.value) {
    return
  }
  isCitationPanelCollapsed.value = shouldCollapseCitationsForViewport()
}

onMounted(() => {
  syncCitationPanelWithViewport()
  void loadKnowledgeTree()
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', syncCitationPanelWithViewport)
  }
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', syncCitationPanelWithViewport)
  }
})

async function loadKnowledgeTree(): Promise<void> {
  try {
    knowledgeFiles.value = await listPdfKnowledgeFiles()
  } catch {
    knowledgeFiles.value = []
  }
}

function buildKnowledgeTree(files: PdfManagedFile[]): PdfKnowledgeNode[] {
  return files
    .filter((file) => !file.parentId)
    .map((file) => toKnowledgeNode(file, files))
}

function toKnowledgeNode(file: PdfManagedFile, files: PdfManagedFile[]): PdfKnowledgeNode {
  const children = files
    .filter((candidate) => candidate.parentId === file.id)
    .map((candidate) => toKnowledgeNode(candidate, files))
  return {
    id: file.id,
    name: file.name,
    kind: file.kind === 'pdf' ? 'pdf' : file.kind === 'folder' ? 'folder' : 'table',
    children: children.length ? children : undefined,
  }
}
</script>

<template>
  <PdfKnowledgeManagementWorkspace
    v-if="workspaceMode === 'management'"
    @change-mode="changeWorkspaceMode"
  />

  <section
    v-else
    class="pdfkb"
    :class="{ 'citation-panel-collapsed': isCitationPanelCollapsed }"
  >
    <PdfKnowledgeSidebar
      :active-view="activeSidebarView"
      :tree="knowledgeTree"
      :recent-chats="recentChats"
      @change-view="changeSidebarView"
      @new-chat="startNewChat"
      @open-management="changeWorkspaceMode('management')"
    />

    <PdfChatWorkspace
      :breadcrumbs="pdfChat.breadcrumbs.value"
      :messages="pdfChat.messages.value"
      :is-answering="pdfChat.isAnswering.value"
      :error-message="pdfChat.errorMessage.value"
      @send-question="pdfChat.sendQuestion"
      @clear-chat="pdfChat.clearChat"
    />

    <PdfSourceCitations
      :citations="pdfChat.citations.value"
      :collapsed="isCitationPanelCollapsed"
      @toggle-collapsed="toggleCitationPanel"
    />
  </section>
</template>
