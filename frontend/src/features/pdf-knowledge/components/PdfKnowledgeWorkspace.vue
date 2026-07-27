<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { listPdfKnowledgeFiles } from '../../../api/pdf-knowledge-api'
import { usePdfChat } from '../composables/use-pdf-chat'
import type {
  PdfBreadcrumbItem,
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

defineProps<{
  isAdmin: boolean
  userEmail: string
  userRoleLabel: string
}>()

const emit = defineEmits<{
  openDiagnostics: []
}>()

const workspaceMode = ref<PdfWorkspaceMode>('management')
const activeSidebarView = ref<PdfSidebarView>('knowledge')
const isCitationPanelCollapsed = ref(false)
const hasUserToggledCitationPanel = ref(false)
const knowledgeFiles = ref<PdfManagedFile[]>([])
const knowledgeTreeError = ref('')
const isKnowledgeTreeStale = ref(true)
const selectedContextId = ref('')
const pdfChat = usePdfChat()

const knowledgeTree = computed<PdfKnowledgeNode[]>(() => {
  return buildKnowledgeTree(knowledgeFiles.value)
})

const recentChats = computed<PdfRecentChat[]>(() => pdfChat.recentChats.value)

const fileLookup = computed(() => {
  return new Map(knowledgeFiles.value.map((file) => [file.id, file]))
})

const chatContextLabel = computed(() => {
  if (!selectedContextId.value) {
    return 'All PDF sources'
  }
  return fileLookup.value.get(selectedContextId.value)?.name ?? 'Selected PDF scope'
})

const chatContextBreadcrumbs = computed<PdfBreadcrumbItem[]>(() => {
  const crumbs = [{ id: 'knowledge-base', label: 'Knowledge Base', icon: 'grid_view' }]
  if (!selectedContextId.value) {
    return [
      ...crumbs,
      { id: 'all-sources', label: 'All PDF sources', icon: 'grid_view', active: true },
    ]
  }
  const path: PdfManagedFile[] = []
  const visited = new Set<string>()
  let current = fileLookup.value.get(selectedContextId.value)
  while (current && !visited.has(current.id)) {
    path.unshift(current)
    visited.add(current.id)
    current = current.parentId ? fileLookup.value.get(current.parentId) : undefined
  }
  return [
    ...crumbs,
    ...path.map((file, index) => ({
      id: file.id,
      label: file.name,
      icon: file.kind === 'folder' ? 'folder_open' : 'description',
      active: index === path.length - 1,
    })),
  ]
})

function shouldCollapseCitationsForViewport(): boolean {
  return typeof window !== 'undefined' && window.innerWidth <= 860
}

function changeSidebarView(view: PdfSidebarView): void {
  activeSidebarView.value = view
}

async function startNewChat(): Promise<void> {
  activeSidebarView.value = 'chats'
  workspaceMode.value = 'chat'
  await refreshKnowledgeTreeIfNeeded()
  await pdfChat.startNewChat()
  syncCitationPanelWithViewport()
}

async function openChat(chatId: string): Promise<void> {
  activeSidebarView.value = 'chats'
  workspaceMode.value = 'chat'
  await refreshKnowledgeTreeIfNeeded()
  await pdfChat.openSession(chatId)
  syncCitationPanelWithViewport()
}

function selectChatContext(fileId: string): void {
  selectedContextId.value = fileId
  pdfChat.setContextFileIds(fileId ? [fileId] : [])
}

function toggleCitationPanel(): void {
  hasUserToggledCitationPanel.value = true
  isCitationPanelCollapsed.value = !isCitationPanelCollapsed.value
}

async function changeWorkspaceMode(mode: PdfWorkspaceMode): Promise<void> {
  workspaceMode.value = mode
  if (mode === 'chat') {
    await refreshKnowledgeTreeIfNeeded()
    syncCitationPanelWithViewport()
  }
}

function markKnowledgeTreeStale(): void {
  isKnowledgeTreeStale.value = true
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
  void pdfChat.loadSessions()
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
    knowledgeTreeError.value = ''
    isKnowledgeTreeStale.value = false
    if (selectedContextId.value && !fileLookup.value.has(selectedContextId.value)) {
      selectChatContext('')
    }
  } catch (error: unknown) {
    knowledgeFiles.value = []
    knowledgeTreeError.value = toErrorMessage(error)
    isKnowledgeTreeStale.value = true
    selectChatContext('')
  }
}

async function refreshKnowledgeTreeIfNeeded(): Promise<void> {
  if (!isKnowledgeTreeStale.value) {
    return
  }
  await loadKnowledgeTree()
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF sources failed to load.'
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
    :is-admin="isAdmin"
    :user-email="userEmail"
    :user-role-label="userRoleLabel"
    @change-mode="changeWorkspaceMode"
    @library-changed="markKnowledgeTreeStale"
    @open-diagnostics="emit('openDiagnostics')"
  />

  <section
    v-else
    class="pdfkb"
    :class="{ 'citation-panel-collapsed': isCitationPanelCollapsed }"
  >
    <PdfKnowledgeSidebar
      :active-view="activeSidebarView"
      :error-message="knowledgeTreeError"
      :selected-context-id="selectedContextId"
      :is-admin="isAdmin"
      :tree="knowledgeTree"
      :recent-chats="recentChats"
      :user-email="userEmail"
      :user-role-label="userRoleLabel"
      @change-view="changeSidebarView"
      @new-chat="startNewChat"
      @open-chat="openChat"
      @open-management="changeWorkspaceMode('management')"
      @select-context="selectChatContext"
    />

    <PdfChatWorkspace
      :breadcrumbs="chatContextBreadcrumbs"
      :context-label="chatContextLabel"
      :messages="pdfChat.messages.value"
      :is-answering="pdfChat.isAnswering.value"
      :enable-deep-thinking="pdfChat.enableDeepThinking.value"
      :error-message="pdfChat.errorMessage.value"
      @send-question="pdfChat.sendQuestion"
      @toggle-deep-thinking="pdfChat.toggleDeepThinking"
      @clear-chat="pdfChat.clearChat"
    />

    <PdfSourceCitations
      :citations="pdfChat.citations.value"
      :collapsed="isCitationPanelCollapsed"
      @toggle-collapsed="toggleCitationPanel"
    />
  </section>
</template>
