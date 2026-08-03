<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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
  mode: PdfWorkspaceMode
  active: boolean
  isAdmin: boolean
}>()

const emit = defineEmits<{
  navigate: [destination: 'pdf-chat' | 'pdf-files']
  notificationsRequested: []
}>()

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
let knowledgeTreeLoadPromise: Promise<void> | null = null
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
  if (isStartingNewChat.value) {
    return
  }
  isStartingNewChat.value = true
  activeSidebarView.value = 'chats'
  try {
    await pdfChat.startNewChat()
    sessionActions.cancelSelection()
    syncCitationPanelWithViewport()
  } finally {
    isStartingNewChat.value = false
  }
}

async function openChat(chatId: string): Promise<void> {
  activeSidebarView.value = 'chats'
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
  emit('navigate', 'pdf-files')
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

watch(
  [() => props.mode, () => props.active],
  ([mode, active]) => {
    if (!active || mode !== 'chat') {
      pdfChat.closeCitationEvidence()
      sessionActions.closeRenameDialog()
      sessionActions.closeDeleteDialog()
      sessionActions.cancelSelection()
      return
    }
    managementFocusTarget.value = undefined
    void refreshKnowledgeTreeIfNeeded()
    syncCitationPanelWithViewport()
  },
  { immediate: true },
)

watch(
  [
    () => pdfChat.selectedContextFileIds.value[0] ?? '',
    () => knowledgeFiles.value,
    () => isKnowledgeTreeStale.value,
  ],
  ([restoredContextId]) => {
    if (!restoredContextId) {
      selectedContextId.value = ''
      return
    }
    if (fileLookup.value.has(restoredContextId)) {
      selectedContextId.value = restoredContextId
      return
    }
    if (!isKnowledgeTreeStale.value) {
      selectedContextId.value = ''
      pdfChat.setContextFileIds([])
    }
  },
  { immediate: true },
)

async function loadKnowledgeTree(): Promise<void> {
  if (knowledgeTreeLoadPromise) {
    return knowledgeTreeLoadPromise
  }
  knowledgeTreeLoadPromise = (async () => {
    try {
      knowledgeFiles.value = await listPdfKnowledgeFiles()
      knowledgeTreeError.value = ''
      isKnowledgeTreeStale.value = false
    } catch (error: unknown) {
      knowledgeFiles.value = []
      knowledgeTreeError.value = toErrorMessage(error)
      isKnowledgeTreeStale.value = true
    } finally {
      knowledgeTreeLoadPromise = null
    }
  })()
  return knowledgeTreeLoadPromise
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
  <div class="pdf-workspace-host">
    <PdfKnowledgeManagementWorkspace
      v-show="mode === 'management'"
      :active="active && mode === 'management'"
      :focus-target="managementFocusTarget"
      :is-admin="isAdmin"
      @library-changed="markKnowledgeTreeStale"
      @notifications-requested="emit('notificationsRequested')"
    />

  <section
    v-show="mode === 'chat'"
    class="pdfkb"
    :class="{ 'citation-panel-collapsed': isCitationPanelCollapsed }"
  >
    <PdfKnowledgeSidebar
      :active-view="activeSidebarView"
      :error-message="knowledgeTreeError"
      :selected-context-id="selectedContextId"
      :is-session-loading="pdfChat.isSessionLoading.value"
      :pending-session-id="pdfChat.pendingSessionId.value"
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
      @select-context="selectChatContext"
    />

    <PdfChatWorkspace
      :active-session-id="pdfChat.activeSessionId.value"
      :breadcrumbs="chatContextBreadcrumbs"
      :context-label="chatContextLabel"
      :turns="pdfChat.turns.value"
      :source-documents="chatSourceDocuments"
      :active-citation-key="pdfChat.activeCitationKey.value"
      :is-answering="pdfChat.isAnswering.value"
      :is-session-loading="pdfChat.isSessionLoading.value"
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
      v-if="mode === 'chat' && pdfChat.citationEvidenceDialog.value"
      :dialog="pdfChat.citationEvidenceDialog.value"
      @close="closeCitationEvidence"
      @retry="pdfChat.retryCitationEvidence"
    />

    <PdfChatSessionDialogs
      v-if="mode === 'chat'"
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
  </div>
</template>
