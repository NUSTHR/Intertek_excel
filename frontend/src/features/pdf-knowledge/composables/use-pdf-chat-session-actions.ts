import { computed, ref, watch, type Ref } from 'vue'

import type { PdfRecentChat } from '../types'
import { reconcilePdfChatSelection } from '../utils/pdf-chat-sessions'
import { toErrorMessage } from './pdf-chat-mappers'

interface PdfChatSessionCommands {
  renameSession: (chat: PdfRecentChat, title: string) => Promise<void>
  setSessionPinned: (chat: PdfRecentChat, pinned: boolean) => Promise<void>
  deleteSessions: (chats: PdfRecentChat[]) => Promise<void>
  setSessionsPinned: (chats: PdfRecentChat[], pinned: boolean) => Promise<void>
}

export function usePdfChatSessionActions(
  chats: Readonly<Ref<PdfRecentChat[]>>,
  commands: PdfChatSessionCommands,
) {
  const selectedSessionIds = ref<Set<string>>(new Set())
  const isSelectionMode = ref(false)
  const busySessionIds = ref<Set<string>>(new Set())
  const pendingRenameChat = ref<PdfRecentChat | null>(null)
  const renameDraft = ref('')
  const renameError = ref('')
  const isRenamePending = ref(false)
  const pendingDeleteChats = ref<PdfRecentChat[]>([])
  const deleteError = ref('')
  const isDeletePending = ref(false)
  const batchError = ref('')
  const isBatchPending = ref(false)

  const selectedChats = computed(() => {
    return chats.value.filter((chat) => selectedSessionIds.value.has(chat.id))
  })

  const isAllSelected = computed(() => {
    return chats.value.length > 0
      && selectedSessionIds.value.size === chats.value.length
  })

  const canSubmitRename = computed(() => {
    const normalized = renameDraft.value.trim()
    return Boolean(
      pendingRenameChat.value
      && normalized
      && normalized.length <= 120
      && normalized !== pendingRenameChat.value.title,
    )
  })

  watch(
    chats,
    (nextChats) => {
      selectedSessionIds.value = reconcilePdfChatSelection(
        selectedSessionIds.value,
        nextChats,
      )
      const currentIds = new Set(nextChats.map((chat) => chat.id))
      busySessionIds.value = new Set(
        Array.from(busySessionIds.value).filter((sessionId) =>
          currentIds.has(sessionId),
        ),
      )
      if (isSelectionMode.value && nextChats.length === 0) {
        cancelSelection()
      }
    },
  )

  function beginSelection(initialSessionId = ''): void {
    isSelectionMode.value = true
    batchError.value = ''
    selectedSessionIds.value = initialSessionId
      ? new Set([initialSessionId])
      : new Set()
  }

  function cancelSelection(): void {
    if (isBatchPending.value || isDeletePending.value) {
      return
    }
    isSelectionMode.value = false
    selectedSessionIds.value = new Set()
    batchError.value = ''
  }

  function toggleSelection(sessionId: string): void {
    if (isBatchPending.value || isDeletePending.value) {
      return
    }
    const nextSelection = new Set(selectedSessionIds.value)
    if (nextSelection.has(sessionId)) {
      nextSelection.delete(sessionId)
    } else {
      nextSelection.add(sessionId)
    }
    selectedSessionIds.value = nextSelection
  }

  function toggleSelectAll(): void {
    if (isBatchPending.value || isDeletePending.value) {
      return
    }
    selectedSessionIds.value = isAllSelected.value
      ? new Set()
      : new Set(chats.value.map((chat) => chat.id))
  }

  function requestRename(chat: PdfRecentChat): void {
    if (busySessionIds.value.has(chat.id)) {
      return
    }
    pendingRenameChat.value = chat
    renameDraft.value = chat.title
    renameError.value = ''
  }

  function closeRenameDialog(): void {
    if (isRenamePending.value) {
      return
    }
    pendingRenameChat.value = null
    renameDraft.value = ''
    renameError.value = ''
  }

  async function submitRename(): Promise<void> {
    const chat = pendingRenameChat.value
    const title = renameDraft.value.trim()
    if (!chat || !canSubmitRename.value || isRenamePending.value) {
      return
    }
    isRenamePending.value = true
    renameError.value = ''
    markBusy([chat.id], true)
    try {
      await commands.renameSession(chat, title)
      pendingRenameChat.value = null
      renameDraft.value = ''
    } catch (error: unknown) {
      renameError.value = toErrorMessage(error)
    } finally {
      markBusy([chat.id], false)
      isRenamePending.value = false
    }
  }

  async function togglePinned(chat: PdfRecentChat): Promise<void> {
    if (busySessionIds.value.has(chat.id)) {
      return
    }
    batchError.value = ''
    markBusy([chat.id], true)
    try {
      await commands.setSessionPinned(chat, !chat.pinnedAt)
    } catch (error: unknown) {
      batchError.value = toErrorMessage(error)
    } finally {
      markBusy([chat.id], false)
    }
  }

  function requestDelete(chatsToDelete: PdfRecentChat[]): void {
    if (
      chatsToDelete.length === 0
      || chatsToDelete.some((chat) => busySessionIds.value.has(chat.id))
    ) {
      return
    }
    pendingDeleteChats.value = [...chatsToDelete]
    deleteError.value = ''
  }

  function closeDeleteDialog(): void {
    if (isDeletePending.value) {
      return
    }
    pendingDeleteChats.value = []
    deleteError.value = ''
  }

  async function confirmDelete(): Promise<void> {
    const chatsToDelete = [...pendingDeleteChats.value]
    if (chatsToDelete.length === 0 || isDeletePending.value) {
      return
    }
    isDeletePending.value = true
    deleteError.value = ''
    markBusy(chatsToDelete.map((chat) => chat.id), true)
    try {
      await commands.deleteSessions(chatsToDelete)
      pendingDeleteChats.value = []
      if (isSelectionMode.value) {
        isSelectionMode.value = false
        selectedSessionIds.value = new Set()
      }
    } catch (error: unknown) {
      deleteError.value = toErrorMessage(error)
    } finally {
      markBusy(chatsToDelete.map((chat) => chat.id), false)
      isDeletePending.value = false
    }
  }

  async function setSelectedPinned(pinned: boolean): Promise<void> {
    const chatsToUpdate = selectedChats.value
    if (chatsToUpdate.length === 0 || isBatchPending.value) {
      return
    }
    isBatchPending.value = true
    batchError.value = ''
    markBusy(chatsToUpdate.map((chat) => chat.id), true)
    try {
      await commands.setSessionsPinned(chatsToUpdate, pinned)
    } catch (error: unknown) {
      batchError.value = toErrorMessage(error)
    } finally {
      markBusy(chatsToUpdate.map((chat) => chat.id), false)
      isBatchPending.value = false
    }
  }

  function markBusy(sessionIds: string[], busy: boolean): void {
    const nextBusyIds = new Set(busySessionIds.value)
    for (const sessionId of sessionIds) {
      if (busy) {
        nextBusyIds.add(sessionId)
      } else {
        nextBusyIds.delete(sessionId)
      }
    }
    busySessionIds.value = nextBusyIds
  }

  return {
    selectedSessionIds,
    selectedChats,
    isSelectionMode,
    isAllSelected,
    busySessionIds,
    pendingRenameChat,
    renameDraft,
    renameError,
    isRenamePending,
    canSubmitRename,
    pendingDeleteChats,
    deleteError,
    isDeletePending,
    batchError,
    isBatchPending,
    beginSelection,
    cancelSelection,
    toggleSelection,
    toggleSelectAll,
    requestRename,
    closeRenameDialog,
    submitRename,
    togglePinned,
    requestDelete,
    closeDeleteDialog,
    confirmDelete,
    setSelectedPinned,
  }
}
