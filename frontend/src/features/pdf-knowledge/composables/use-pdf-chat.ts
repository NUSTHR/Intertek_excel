import { computed, ref } from 'vue'

import {
  answerPdfQuestion,
  batchMutatePdfChatSessions,
  cancelPdfChatRequest,
  createPdfChatSession,
  deletePdfChatSession,
  getPdfChatSession,
  listPdfChatSessions,
  listPdfChatSessionTurns,
  listPdfDocumentChunks,
  renamePdfChatSession,
  setPdfChatSessionPinned,
} from '../../../api/pdf-knowledge-api'
import { createRequestCoordinator } from '../../../app/composables/use-request-coordinator'
import type {
  PdfChatSession,
  PdfChatTurnView,
  PdfCitation,
  PdfCitationEvidenceDialogState,
  PdfRecentChat,
  PdfSelectedDocument,
} from '../types'
import {
  dedupeFileIds,
  newRequestId,
  sameFileIds,
  toErrorMessage,
} from './pdf-chat-mappers'
import {
  toAnsweredChatTurn,
  toChatTurnView,
  toFailedChatTurn,
  toPendingChatTurn,
} from '../utils/pdf-chat-view'
import {
  normalizePdfDisplayText,
  optionalTrimmedText,
} from '../utils/pdf-citation-presentation'
import { sortPdfChatSessions } from '../utils/pdf-chat-sessions'

export function usePdfChat() {
  const turns = ref<PdfChatTurnView[]>([])
  const sessions = ref<PdfChatSession[]>([])
  const activeSessionId = ref('')
  const activeTurnId = ref('')
  const activeCitationKey = ref('')
  const citationEvidenceDialog = ref<PdfCitationEvidenceDialogState | null>(null)
  const selectedContextFileIds = ref<string[]>([])
  const enableDeepThinking = ref(false)
  const isAnswering = ref(false)
  const isSessionLoading = ref(false)
  const errorMessage = ref('')
  const activeRequestId = ref('')
  const answerRequests = createRequestCoordinator()
  const sessionNavigationRequests = createRequestCoordinator()
  const sessionListRequests = createRequestCoordinator()
  const citationEvidenceRequests = createRequestCoordinator()

  const recentChats = computed<PdfRecentChat[]>(() => {
    return sessions.value.map((session) => ({
      id: session.sessionId,
      title: session.title || 'New chat',
      pinnedAt: session.pinnedAt,
      updatedAt: session.updatedAt,
      revision: session.revision,
    }))
  })

  const activeTurn = computed<PdfChatTurnView | undefined>(() => {
    const selected = turns.value.find(
      (turn) => turn.turnId === activeTurnId.value && turn.status === 'complete',
    )
    return selected ?? latestCompleteTurn()
  })

  const citations = computed<PdfCitation[]>(() => {
    return activeTurn.value?.answer?.citations ?? []
  })

  const selectedDocuments = computed<PdfSelectedDocument[]>(() => {
    return activeTurn.value?.answer?.selectedDocuments ?? []
  })

  function setContextFileIds(fileIds: string[]): void {
    const nextFileIds = dedupeFileIds(fileIds)
    if (sameFileIds(nextFileIds, selectedContextFileIds.value)) {
      return
    }
    cancelAnswer()
    selectedContextFileIds.value = nextFileIds
    clearCitationSelection()
  }

  function toggleDeepThinking(): void {
    if (isAnswering.value) {
      return
    }
    enableDeepThinking.value = !enableDeepThinking.value
  }

  async function sendQuestion(question: string): Promise<void> {
    const normalizedQuestion = question.trim()
    if (!normalizedQuestion || isAnswering.value) {
      return
    }
    const request = answerRequests.begin()
    const requestId = newRequestId()
    const pendingTurnId = `pending:${requestId}`
    activeRequestId.value = requestId
    const requestContextFileIds = [...selectedContextFileIds.value]
    const requestDeepThinking = enableDeepThinking.value
    let requestSessionId = activeSessionId.value
    errorMessage.value = ''
    turns.value = [
      ...turns.value,
      toPendingChatTurn(pendingTurnId, requestSessionId, normalizedQuestion),
    ]
    isAnswering.value = true
    try {
      const session = requestSessionId
        ? undefined
        : await createPdfChatSession(request.signal)
      if (!request.isCurrent()) {
        return
      }
      if (session) {
        requestSessionId = session.sessionId
        activeSessionId.value = requestSessionId
        upsertSession(session)
        updateTurnSessionId(pendingTurnId, requestSessionId)
      }
      const answer = await answerPdfQuestion({
        question: normalizedQuestion,
        sessionId: requestSessionId || undefined,
        fileIds: requestContextFileIds,
        enableDeepThinking: requestDeepThinking,
        requestId,
        signal: request.signal,
      })
      if (
        !request.isCurrent()
        || activeSessionId.value !== requestSessionId
        || !sameFileIds(selectedContextFileIds.value, requestContextFileIds)
      ) {
        return
      }
      const answeredTurn = toAnsweredChatTurn(
        answer,
        answer.requestId || requestId,
        requestSessionId,
        normalizedQuestion,
      )
      replaceTurn(pendingTurnId, answeredTurn)
      activeTurnId.value = answeredTurn.turnId
      clearCitationSelection()
      try {
        const authoritativeSession = await getPdfChatSession(
          requestSessionId,
          request.signal,
        )
        if (
          request.isCurrent()
          && activeSessionId.value === requestSessionId
        ) {
          upsertSession(authoritativeSession)
          selectedContextFileIds.value = [
            ...authoritativeSession.contextFileIds,
          ]
        }
      } catch {
        // The answer is already committed. The next session refresh will
        // reconcile metadata if this best-effort read is interrupted.
      }
    } catch (error: unknown) {
      if (!request.isCurrent()) {
        return
      }
      const message = toErrorMessage(error, normalizedQuestion)
      errorMessage.value = message
      replaceTurn(
        pendingTurnId,
        toFailedChatTurn(
          pendingTurnId,
          requestSessionId,
          normalizedQuestion,
          message,
        ),
      )
    } finally {
      if (request.isCurrent()) {
        isAnswering.value = false
        if (activeRequestId.value === requestId) {
          activeRequestId.value = ''
        }
      }
    }
  }

  function selectCitation(turnId: string, citationId: string): void {
    const turn = turns.value.find(
      (candidate) => candidate.turnId === turnId && candidate.status === 'complete',
    )
    const citation = turn?.answer?.citations.find(
      (candidate) => candidate.citationId === citationId,
    )
    if (!turn || !citation) {
      return
    }
    activeTurnId.value = turn.turnId
    activeCitationKey.value = citation.key
  }

  function openCitationEvidence(citation: PdfCitation): void {
    selectCitation(citation.turnId, citation.citationId)
    if (activeCitationKey.value !== citation.key) {
      return
    }
    citationEvidenceDialog.value = {
      citation,
      status: 'loading',
    }
    void loadCitationEvidence(citation)
  }

  function retryCitationEvidence(): void {
    const citation = citationEvidenceDialog.value?.citation
    if (!citation) {
      return
    }
    openCitationEvidence(citation)
  }

  function closeCitationEvidence(): void {
    citationEvidenceRequests.cancel()
    citationEvidenceDialog.value = null
  }

  async function loadCitationEvidence(citation: PdfCitation): Promise<void> {
    const request = citationEvidenceRequests.begin()
    try {
      const chunks = await listPdfDocumentChunks(citation.fileId, request.signal)
      if (
        !request.isCurrent()
        || citationEvidenceDialog.value?.citation.key !== citation.key
      ) {
        return
      }
      const chunk = chunks.find((candidate) => candidate.id === citation.chunkId)
      if (!chunk) {
        citationEvidenceDialog.value = {
          citation,
          status: 'failed',
          errorMessage: (
            'This indexed evidence is no longer available. The PDF may have been reparsed.'
          ),
        }
        return
      }
      citationEvidenceDialog.value = {
        citation,
        status: 'ready',
        evidence: {
          citationKey: citation.key,
          chunkId: chunk.id,
          fileId: citation.fileId,
          text: normalizePdfDisplayText(chunk.text),
          title: normalizePdfDisplayText(chunk.title),
          pageLabel: optionalTrimmedText(chunk.pageLabel),
        },
      }
    } catch (error: unknown) {
      if (
        request.isCurrent()
        && citationEvidenceDialog.value?.citation.key === citation.key
      ) {
        citationEvidenceDialog.value = {
          citation,
          status: 'failed',
          errorMessage: toErrorMessage(error),
        }
      }
    }
  }

  async function loadSessions(): Promise<void> {
    const request = sessionListRequests.begin()
    try {
      const nextSessions = await listPdfChatSessions(request.signal)
      if (request.isCurrent()) {
        sessions.value = sortPdfChatSessions(nextSessions)
      }
    } catch (error: unknown) {
      if (request.isCurrent()) {
        errorMessage.value = toErrorMessage(error)
      }
    }
  }

  async function startNewChat(): Promise<void> {
    if (isSessionLoading.value) {
      return
    }
    cancelAnswer()
    const request = sessionNavigationRequests.begin()
    errorMessage.value = ''
    isSessionLoading.value = true
    try {
      const session = await createPdfChatSession(request.signal)
      if (!request.isCurrent()) {
        return
      }
      upsertSession(session)
      activeSessionId.value = session.sessionId
      turns.value = []
      activeTurnId.value = ''
      clearCitationSelection()
    } catch (error: unknown) {
      if (request.isCurrent()) {
        errorMessage.value = toErrorMessage(error)
      }
    } finally {
      if (request.isCurrent()) {
        isSessionLoading.value = false
      }
    }
  }

  async function openSession(sessionId: string): Promise<void> {
    cancelAnswer()
    const request = sessionNavigationRequests.begin()
    errorMessage.value = ''
    isSessionLoading.value = true
    try {
      const [nextTurns, session] = await Promise.all([
        listPdfChatSessionTurns(sessionId, request.signal),
        getPdfChatSession(sessionId, request.signal),
      ])
      if (!request.isCurrent()) {
        return
      }
      upsertSession(session)
      activeSessionId.value = sessionId
      turns.value = nextTurns.map(toChatTurnView)
      activeTurnId.value = latestCompleteTurn()?.turnId ?? ''
      clearCitationSelection()
      selectedContextFileIds.value = [...session.contextFileIds]
    } catch (error: unknown) {
      if (request.isCurrent()) {
        errorMessage.value = toErrorMessage(error)
      }
    } finally {
      if (request.isCurrent()) {
        isSessionLoading.value = false
      }
    }
  }

  async function renameSession(
    sessionId: string,
    title: string,
    expectedRevision: number,
  ): Promise<void> {
    const updated = await renamePdfChatSession(
      sessionId,
      title,
      expectedRevision,
    )
    upsertSession(updated)
  }

  async function setSessionPinned(
    sessionId: string,
    pinned: boolean,
    expectedRevision: number,
  ): Promise<void> {
    const updated = await setPdfChatSessionPinned(
      sessionId,
      pinned,
      expectedRevision,
    )
    upsertSession(updated)
  }

  async function deleteSession(
    sessionId: string,
    expectedRevision: number,
  ): Promise<void> {
    if (activeSessionId.value === sessionId) {
      cancelAnswer()
    }
    await deletePdfChatSession(sessionId, expectedRevision)
    await applyDeletedSessions([sessionId])
  }

  async function batchMutateSessions(
    action: 'pin' | 'unpin' | 'delete',
    items: Array<{ sessionId: string; expectedRevision: number }>,
  ): Promise<void> {
    if (
      action === 'delete'
      && items.some((item) => item.sessionId === activeSessionId.value)
    ) {
      cancelAnswer()
    }
    const result = await batchMutatePdfChatSessions(action, items)
    if (result.updatedSessions.length > 0) {
      const updatedIds = new Set(
        result.updatedSessions.map((session) => session.sessionId),
      )
      sessions.value = sortPdfChatSessions([
        ...result.updatedSessions,
        ...sessions.value.filter(
          (session) => !updatedIds.has(session.sessionId),
        ),
      ])
    }
    if (result.deletedSessionIds.length > 0) {
      await applyDeletedSessions(result.deletedSessionIds)
    }
  }

  function clearChat(): void {
    cancelAnswer()
    sessionNavigationRequests.cancel()
    isSessionLoading.value = false
    resetChatState()
    errorMessage.value = ''
  }

  function cancelAnswer(): void {
    const requestId = activeRequestId.value
    activeRequestId.value = ''
    if (requestId) {
      void cancelPdfChatRequest(requestId).catch(() => undefined)
    }
    answerRequests.cancel()
    isAnswering.value = false
    turns.value = turns.value.filter((turn) => turn.status !== 'pending')
  }

  function clearCitationSelection(): void {
    closeCitationEvidence()
    activeCitationKey.value = ''
  }

  function cancelActiveOperations(): void {
    cancelAnswer()
    sessionNavigationRequests.cancel()
    clearCitationSelection()
    isSessionLoading.value = false
  }

  function dispose(): void {
    cancelActiveOperations()
    sessionListRequests.cancel()
  }

  function resetChatState(): void {
    activeSessionId.value = ''
    activeTurnId.value = ''
    turns.value = []
    clearCitationSelection()
  }

  function latestCompleteTurn(): PdfChatTurnView | undefined {
    for (let index = turns.value.length - 1; index >= 0; index -= 1) {
      const turn = turns.value[index]
      if (turn?.status === 'complete') {
        return turn
      }
    }
    return undefined
  }

  function replaceTurn(turnId: string, nextTurn: PdfChatTurnView): void {
    turns.value = turns.value.map((turn) => (
      turn.turnId === turnId ? nextTurn : turn
    ))
  }

  function updateTurnSessionId(turnId: string, sessionId: string): void {
    turns.value = turns.value.map((turn) => (
      turn.turnId === turnId ? { ...turn, sessionId } : turn
    ))
  }

  function upsertSession(session: PdfChatSession): void {
    sessions.value = sortPdfChatSessions([
      session,
      ...sessions.value.filter((item) => item.sessionId !== session.sessionId),
    ])
  }

  async function applyDeletedSessions(sessionIds: string[]): Promise<void> {
    const deletedIds = new Set(sessionIds)
    const deletedActiveSession = deletedIds.has(activeSessionId.value)
    sessions.value = sortPdfChatSessions(
      sessions.value.filter((session) => !deletedIds.has(session.sessionId)),
    )
    if (!deletedActiveSession) {
      return
    }
    resetChatState()
    const nextSessionId = sessions.value[0]?.sessionId
    if (nextSessionId) {
      await openSession(nextSessionId)
    }
  }

  return {
    turns,
    citations,
    selectedDocuments,
    sessions,
    recentChats,
    activeSessionId,
    activeTurnId,
    activeCitationKey,
    citationEvidenceDialog,
    selectedContextFileIds,
    enableDeepThinking,
    isAnswering,
    isSessionLoading,
    errorMessage,
    setContextFileIds,
    toggleDeepThinking,
    loadSessions,
    startNewChat,
    openSession,
    renameSession,
    setSessionPinned,
    deleteSession,
    batchMutateSessions,
    sendQuestion,
    selectCitation,
    openCitationEvidence,
    retryCitationEvidence,
    closeCitationEvidence,
    clearChat,
    cancelActiveOperations,
    dispose,
  }
}
