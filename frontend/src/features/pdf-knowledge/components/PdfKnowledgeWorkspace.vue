<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { listPdfKnowledgeFiles } from '../../../api/pdf-knowledge-api'
import { ExcelWorkspaceApiError } from '../../../api/errors'
import { usePdfChat } from '../composables/use-pdf-chat'
import { usePdfChatSessionActions } from '../composables/use-pdf-chat-session-actions'
import { shouldDefaultCollapsePdfCitations } from '../utils/pdf-citation-layout'
import { buildPdfKnowledgeTree } from '../utils/pdf-tree'
import type {
  PdfBreadcrumbItem,
  PdfChatSourceDocument,
  PdfKnowledgeNode,
  PdfManagementFocusTarget,
  PdfManagedFile,
  PdfRecentChat,
  PdfSidebarView,
  PdfWorkspaceMode,
} from '../types'
import PdfChatWorkspace from './PdfChatWorkspace.vue'
import PdfChatSessionDialogs from './PdfChatSessionDialogs.vue'
import PdfCitationEvidenceDialog from './PdfCitationEvidenceDialog.vue'
import PdfKnowledgeManagementWorkspace from './PdfKnowledgeManagementWorkspace.vue'
import PdfKnowledgeSidebar from './PdfKnowledgeSidebar.vue'
import PdfSourceCitations from './PdfSourceCitations.vue'

const props = defineProps<{
  entryMode: PdfWorkspaceMode
  isAdmin: boolean
  userEmail: string
  userRoleLabel: string
}>()

const emit = defineEmits<{
  openExcelChat: []
  openDiagnostics: []
  logout: []
}>()

const workspaceMode = ref<PdfWorkspaceMode>(props.entryMode)
const activeSidebarView = ref<PdfSidebarView>('knowledge')
const isCitationPanelCollapsed = ref(false)
const hasUserToggledCitationPanel = ref(false)
const citationFocusRequestId = ref(0)
const knowledgeFiles = ref<PdfManagedFile[]>([])
const knowledgeTreeError = ref('')
const isKnowledgeTreeStale = ref(true)
const selectedContextId = ref('')
const isStartingNewChat = ref(false)
const managementFocusTarget = ref<PdfManagementFocusTarget>()
let managementFocusRequestId = 0
const pdfChat = usePdfChat()

const knowledgeTree = computed<PdfKnowledgeNode[]>(() => {
  return buildPdfKnowledgeTree(knowledgeFiles.value)
})

const recentChats = computed<PdfRecentChat[]>(() => pdfChat.recentChats.value)

const sessionActions = usePdfChatSessionActions(recentChats, {
  renameSession: (chat, title) => runSessionMutation(() =>
    pdfChat.renameSession(chat.id, title, chat.revision)),
  setSessionPinned: (chat, pinned) => runSessionMutation(() =>
    pdfChat.setSessionPinned(chat.id, pinned, chat.revision)),
  deleteSessions: (chats) => runSessionMutation(async () => {
    if (chats.length === 1) {
      const chat = chats[0]
      if (chat) {
        await pdfChat.deleteSession(chat.id, chat.revision)
      }
      return
    }
    await pdfChat.batchMutateSessions(
      'delete',
      chats.map((chat) => ({
        sessionId: chat.id,
        expectedRevision: chat.revision,
      })),
    )
  }),
  setSessionsPinned: (chats, pinned) => runSessionMutation(() =>
    pdfChat.batchMutateSessions(
      pinned ? 'pin' : 'unpin',
      chats.map((chat) => ({
        sessionId: chat.id,
        expectedRevision: chat.revision,
      })),
    )),
})

const fileLookup = computed(() => {
  return new Map(knowledgeFiles.value.map((file) => [file.id, file]))
})

const chatSourceDocuments = computed<PdfChatSourceDocument[]>(() => {
  const turnId = pdfChat.activeTurnId.value || 'latest'
  return pdfChat.selectedDocuments.value.map((document) => ({
    key: `${turnId}:${document.fileId}:${document.versionId}`,
    fileId: document.fileId,
    versionId: document.versionId,
    title: fileLookup.value.get(document.fileId)?.name ?? document.fileId,
    reason: document.reason,
    confidence: document.confidence,
  }))
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
  return typeof window !== 'undefined'
    && shouldDefaultCollapsePdfCitations(window.innerWidth)
}

function changeSidebarView(view: PdfSidebarView): void {
  activeSidebarView.value = view
}

async function startNewChat(): Promise<void> {
  if (isStartingNewChat.value || pdfChat.isSessionLoading.value) {
    return
  }
  isStartingNewChat.value = true
  activeSidebarView.value = 'chats'
  workspaceMode.value = 'chat'
  try {
    await refreshKnowledgeTreeIfNeeded()
    await pdfChat.startNewChat()
    sessionActions.cancelSelection()
    syncCitationPanelWithViewport()
  } finally {
    isStartingNewChat.value = false
  }
}

async function openChat(chatId: string): Promise<void> {
  activeSidebarView.value = 'chats'
  workspaceMode.value = 'chat'
  await refreshKnowledgeTreeIfNeeded()
  await pdfChat.openSession(chatId)
  const restoredContextId = pdfChat.selectedContextFileIds.value[0] ?? ''
  selectedContextId.value = fileLookup.value.has(restoredContextId)
    ? restoredContextId
    : ''
  if (selectedContextId.value !== restoredContextId) {
    pdfChat.setContextFileIds([])
  }
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

function selectChatCitation(turnId: string, citationId: string): void {
  if (isCitationPanelCollapsed.value) {
    isCitationPanelCollapsed.value = false
  }
  pdfChat.selectCitation(turnId, citationId)
}

function closeCitationEvidence(): void {
  pdfChat.closeCitationEvidence()
  citationFocusRequestId.value += 1
}

function openSourceDocument(document: PdfChatSourceDocument): void {
  managementFocusRequestId += 1
  managementFocusTarget.value = {
    requestId: managementFocusRequestId,
    fileId: document.fileId,
  }
  void changeWorkspaceMode('management')
}

async function changeWorkspaceMode(mode: PdfWorkspaceMode): Promise<void> {
  if (mode === 'management') {
    pdfChat.cancelActiveOperations()
  } else {
    managementFocusTarget.value = undefined
  }
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
  pdfChat.dispose()
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

async function runSessionMutation(action: () => Promise<void>): Promise<void> {
  try {
    await action()
  } catch (error: unknown) {
    if (
      error instanceof ExcelWorkspaceApiError
      && error.code === 'CHAT_SESSION_REVISION_CONFLICT'
    ) {
      await pdfChat.loadSessions()
    }
    throw error
  }
}

</script>

<template>
  <PdfKnowledgeManagementWorkspace
    v-if="workspaceMode === 'management'"
    :focus-target="managementFocusTarget"
    :is-admin="isAdmin"
    :user-email="userEmail"
    :user-role-label="userRoleLabel"
    @change-mode="changeWorkspaceMode"
    @library-changed="markKnowledgeTreeStale"
    @open-diagnostics="emit('openDiagnostics')"
    @logout="emit('logout')"
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
      :is-session-loading="pdfChat.isSessionLoading.value"
      :is-starting-new-chat="isStartingNewChat"
      :active-session-id="pdfChat.activeSessionId.value"
      :tree="knowledgeTree"
      :recent-chats="recentChats"
      :is-chat-selection-mode="sessionActions.isSelectionMode.value"
      :is-all-chats-selected="sessionActions.isAllSelected.value"
      :is-chat-batch-pending="sessionActions.isBatchPending.value"
      :selected-session-ids="sessionActions.selectedSessionIds.value"
      :busy-session-ids="sessionActions.busySessionIds.value"
      :session-action-error="sessionActions.batchError.value"
      :user-email="userEmail"
      :user-role-label="userRoleLabel"
      @change-view="changeSidebarView"
      @new-chat="startNewChat"
      @open-chat="openChat"
      @begin-chat-selection="sessionActions.beginSelection"
      @cancel-chat-selection="sessionActions.cancelSelection"
      @toggle-chat-selection="sessionActions.toggleSelection"
      @toggle-select-all-chats="sessionActions.toggleSelectAll"
      @rename-chat="sessionActions.requestRename"
      @toggle-chat-pinned="sessionActions.togglePinned"
      @delete-chat="(chat) => sessionActions.requestDelete([chat])"
      @pin-selected-chats="sessionActions.setSelectedPinned(true)"
      @unpin-selected-chats="sessionActions.setSelectedPinned(false)"
      @delete-selected-chats="
        sessionActions.requestDelete(sessionActions.selectedChats.value)
      "
      @open-excel-chat="emit('openExcelChat')"
      @open-management="changeWorkspaceMode('management')"
      @select-context="selectChatContext"
      @logout="emit('logout')"
    />

    <PdfChatWorkspace
      :breadcrumbs="chatContextBreadcrumbs"
      :context-label="chatContextLabel"
      :turns="pdfChat.turns.value"
      :source-documents="chatSourceDocuments"
      :active-citation-key="pdfChat.activeCitationKey.value"
      :is-answering="pdfChat.isAnswering.value"
      :enable-deep-thinking="pdfChat.enableDeepThinking.value"
      :error-message="pdfChat.errorMessage.value"
      @send-question="pdfChat.sendQuestion"
      @select-citation="selectChatCitation"
      @select-source-document="openSourceDocument"
      @toggle-deep-thinking="pdfChat.toggleDeepThinking"
      @clear-chat="pdfChat.clearChat"
    />

    <PdfSourceCitations
      :citations="pdfChat.citations.value"
      :collapsed="isCitationPanelCollapsed"
      :active-citation-key="pdfChat.activeCitationKey.value"
      :focus-request-id="citationFocusRequestId"
      @open-citation="pdfChat.openCitationEvidence"
      @toggle-collapsed="toggleCitationPanel"
    />

    <PdfCitationEvidenceDialog
      v-if="pdfChat.citationEvidenceDialog.value"
      :dialog="pdfChat.citationEvidenceDialog.value"
      @close="closeCitationEvidence"
      @retry="pdfChat.retryCitationEvidence"
    />

    <PdfChatSessionDialogs
      :active-session-id="pdfChat.activeSessionId.value"
      :pending-rename-chat="sessionActions.pendingRenameChat.value"
      :rename-draft="sessionActions.renameDraft.value"
      :rename-error="sessionActions.renameError.value"
      :is-rename-pending="sessionActions.isRenamePending.value"
      :can-submit-rename="sessionActions.canSubmitRename.value"
      :pending-delete-chats="sessionActions.pendingDeleteChats.value"
      :delete-error="sessionActions.deleteError.value"
      :is-delete-pending="sessionActions.isDeletePending.value"
      @update-rename-draft="sessionActions.renameDraft.value = $event"
      @close-rename="sessionActions.closeRenameDialog"
      @submit-rename="sessionActions.submitRename"
      @close-delete="sessionActions.closeDeleteDialog"
      @confirm-delete="sessionActions.confirmDelete"
    />
  </section>
</template>
