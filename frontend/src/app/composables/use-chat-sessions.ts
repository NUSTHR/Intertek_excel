import { computed, ref } from 'vue'

import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  renameChatSession,
  setChatSessionPinned,
} from '../../api/chat-api'
import { toErrorMessage } from '../workspace-utils'
import type { ChatSession } from '../../types/chat'

interface ChatSessionOptions {
  clearFeedback?: () => void
  showFeedback?: (tone: 'success', message: string) => void
  onSessionActivated?: (session: ChatSession) => void
  onActiveSessionDeleted?: () => void
}

export function useChatSessions(options: ChatSessionOptions = {}) {
  const chatSessions = ref<ChatSession[]>([])
  const activeChatSessionId = ref<string>('')
  const chatSessionError = ref<string>('')
  const isChatSessionLoading = ref<boolean>(false)
  let chatSessionListRequestId = 0

  const activeChatSession = computed(() => {
    return (
      chatSessions.value.find((session) => session.session_id === activeChatSessionId.value) ??
      null
    )
  })

  async function loadChatSessions(preferredSessionId: string | null = null): Promise<void> {
    const requestId = ++chatSessionListRequestId
    chatSessionError.value = ''
    options.clearFeedback?.()
    isChatSessionLoading.value = true
    try {
      const sessions = await listChatSessions()
      if (requestId !== chatSessionListRequestId) {
        return
      }
      chatSessions.value = sortChatSessions(sessions)
      const nextActiveSessionId = preferredSessionId || activeChatSessionId.value
      const activeStillExists = chatSessions.value.some(
        (session) => session.session_id === nextActiveSessionId,
      )
      if (nextActiveSessionId && activeStillExists) {
        activeChatSessionId.value = nextActiveSessionId
        return
      }
      activeChatSessionId.value = chatSessions.value[0]?.session_id ?? ''
    } catch (error: unknown) {
      if (requestId === chatSessionListRequestId) {
        chatSessionError.value = toErrorMessage(error)
      }
    } finally {
      if (requestId === chatSessionListRequestId) {
        isChatSessionLoading.value = false
      }
    }
  }

  async function startNewChatSession(): Promise<ChatSession | null> {
    chatSessionError.value = ''
    options.clearFeedback?.()
    isChatSessionLoading.value = true
    try {
      const session = await createChatSession()
      upsertChatSession(session)
      activeChatSessionId.value = session.session_id
      options.onSessionActivated?.(session)
      return session
    } catch (error: unknown) {
      chatSessionError.value = toErrorMessage(error)
      return null
    } finally {
      isChatSessionLoading.value = false
    }
  }

  async function toggleChatSessionPin(session: ChatSession): Promise<void> {
    const pinned = !session.pinned_at
    await updateChatSession(
      () => setChatSessionPinned(session.session_id, pinned),
      pinned ? 'Chat pinned.' : 'Chat unpinned.',
    )
  }

  async function confirmDeleteChatSession(session: ChatSession): Promise<boolean> {
    chatSessionError.value = ''
    options.clearFeedback?.()
    isChatSessionLoading.value = true
    try {
      await deleteChatSession(session.session_id)
      chatSessions.value = chatSessions.value.filter(
        (item) => item.session_id !== session.session_id,
      )
      if (activeChatSessionId.value === session.session_id) {
        activeChatSessionId.value = chatSessions.value[0]?.session_id ?? ''
        options.onActiveSessionDeleted?.()
      }
      options.showFeedback?.('success', 'Chat deleted.')
      return true
    } catch (error: unknown) {
      chatSessionError.value = toErrorMessage(error)
      return false
    } finally {
      isChatSessionLoading.value = false
    }
  }

  function handleChatSessionCreated(session: ChatSession): void {
    upsertChatSession(session)
    activeChatSessionId.value = session.session_id
  }

  async function handleChatSessionTitleSuggested(
    sessionId: string,
    title: string,
  ): Promise<void> {
    const session = chatSessions.value.find((item) => item.session_id === sessionId)
    if (!session || session.title !== 'New chat') {
      return
    }
    await updateChatSession(() => renameChatSession(sessionId, title))
  }

  async function renameActiveChatSession(
    session: ChatSession,
    title: string,
  ): Promise<boolean> {
    return updateChatSession(
      () => renameChatSession(session.session_id, title),
      'Chat renamed.',
    )
  }

  async function updateChatSession(
    action: () => Promise<ChatSession>,
    successMessage = '',
  ): Promise<boolean> {
    chatSessionError.value = ''
    options.clearFeedback?.()
    isChatSessionLoading.value = true
    try {
      const session = await action()
      upsertChatSession(session)
      if (successMessage) {
        options.showFeedback?.('success', successMessage)
      }
      return true
    } catch (error: unknown) {
      chatSessionError.value = toErrorMessage(error)
      return false
    } finally {
      isChatSessionLoading.value = false
    }
  }

  function selectChatSession(session: ChatSession): void {
    activeChatSessionId.value = session.session_id
  }

  function resetChatSessions(): void {
    chatSessions.value = []
    activeChatSessionId.value = ''
    chatSessionError.value = ''
    isChatSessionLoading.value = false
    chatSessionListRequestId += 1
  }

  function upsertChatSession(session: ChatSession): void {
    const sessions = chatSessions.value.filter((item) => item.session_id !== session.session_id)
    chatSessions.value = sortChatSessions([session, ...sessions])
  }

  function sortChatSessions(sessions: ChatSession[]): ChatSession[] {
    return [...sessions].sort((left, right) => {
      if (left.pinned_at && !right.pinned_at) {
        return -1
      }
      if (!left.pinned_at && right.pinned_at) {
        return 1
      }
      const leftDate = left.pinned_at || left.updated_at
      const rightDate = right.pinned_at || right.updated_at
      return rightDate.localeCompare(leftDate)
    })
  }

  return {
    chatSessions,
    activeChatSessionId,
    activeChatSession,
    chatSessionError,
    isChatSessionLoading,
    loadChatSessions,
    startNewChatSession,
    selectChatSession,
    toggleChatSessionPin,
    confirmDeleteChatSession,
    handleChatSessionCreated,
    handleChatSessionTitleSuggested,
    renameActiveChatSession,
    updateChatSession,
    resetChatSessions,
    upsertChatSession,
  }
}
