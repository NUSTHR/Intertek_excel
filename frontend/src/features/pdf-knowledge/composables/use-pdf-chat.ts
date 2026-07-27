import { computed, ref } from 'vue'

import {
  answerPdfQuestion,
  createPdfChatSession,
  deletePdfChatSession,
  listPdfChatSessions,
  listPdfChatSessionTurns,
  renamePdfChatSession,
  setPdfChatSessionPinned,
} from '../../../api/pdf-knowledge-api'
import type {
  PdfChatAnswer,
  PdfChatMessage,
  PdfChatSession,
  PdfChatTurn,
  PdfCitation,
  PdfRecentChat,
} from '../types'

const defaultRetrievalLimit = 8

export function usePdfChat() {
  const messages = ref<PdfChatMessage[]>([])
  const citations = ref<PdfCitation[]>([])
  const sessions = ref<PdfChatSession[]>([])
  const activeSessionId = ref('')
  const selectedContextFileIds = ref<string[]>([])
  const enableDeepThinking = ref(false)
  const isAnswering = ref(false)
  const errorMessage = ref('')

  const recentChats = computed<PdfRecentChat[]>(() => {
    return sessions.value.map((session) => ({
      id: session.sessionId,
      title: session.title || 'New chat',
      pinnedAt: session.pinnedAt,
    }))
  })

  const breadcrumbs = computed(() => {
    const activeCitation = citations.value[0]
    return [
      { id: 'knowledge-base', label: 'Knowledge Base', icon: 'grid_view' },
      {
        id: activeCitation?.id ?? 'pdf-chat',
        label: activeCitation?.fileName ?? 'PDF Chat',
        icon: activeCitation ? 'description' : 'chat_bubble',
        active: true,
      },
    ]
  })

  function setContextFileIds(fileIds: string[]): void {
    selectedContextFileIds.value = dedupeFileIds(fileIds)
    citations.value = []
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
    errorMessage.value = ''
    messages.value = [
      ...messages.value,
      {
        id: newMessageId('user'),
        role: 'user',
        content: normalizedQuestion,
      },
    ]
    isAnswering.value = true
    try {
      const session = activeSessionId.value
        ? undefined
        : await createPdfChatSession()
      if (session) {
        activeSessionId.value = session.sessionId
        sessions.value = [session, ...sessions.value]
      }
      const answer = await answerPdfQuestion({
        question: normalizedQuestion,
        sessionId: activeSessionId.value || undefined,
        fileIds: selectedContextFileIds.value,
        retrievalLimit: defaultRetrievalLimit,
        enableDeepThinking: enableDeepThinking.value,
      })
      citations.value = toSourceCitations(answer)
      messages.value = [...messages.value, toAssistantMessage(answer)]
    } catch (error: unknown) {
      const message = toErrorMessage(error)
      errorMessage.value = message
      messages.value = [
        ...messages.value,
        {
          id: newMessageId('assistant'),
          role: 'assistant',
          content: message,
          error: true,
        },
      ]
    } finally {
      isAnswering.value = false
    }
  }

  async function loadSessions(): Promise<void> {
    try {
      sessions.value = await listPdfChatSessions()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function startNewChat(): Promise<void> {
    const session = await createPdfChatSession()
    sessions.value = [session, ...sessions.value.filter((item) => item.sessionId !== session.sessionId)]
    activeSessionId.value = session.sessionId
    messages.value = []
    citations.value = []
    errorMessage.value = ''
  }

  async function openSession(sessionId: string): Promise<void> {
    const turns = await listPdfChatSessionTurns(sessionId)
    activeSessionId.value = sessionId
    messages.value = turns.flatMap(toMessagesFromTurn)
    const lastAnswer = turns.at(-1)?.answer
    citations.value = lastAnswer ? toSourceCitations(lastAnswer) : []
    errorMessage.value = ''
  }

  async function renameSession(sessionId: string, title: string): Promise<void> {
    const updated = await renamePdfChatSession(sessionId, title)
    sessions.value = sessions.value.map((session) =>
      session.sessionId === sessionId ? updated : session,
    )
  }

  async function toggleSessionPinned(sessionId: string): Promise<void> {
    const session = sessions.value.find((item) => item.sessionId === sessionId)
    if (!session) {
      return
    }
    const updated = await setPdfChatSessionPinned(sessionId, !session.pinnedAt)
    sessions.value = [updated, ...sessions.value.filter((item) => item.sessionId !== sessionId)]
  }

  async function deleteSession(sessionId: string): Promise<void> {
    await deletePdfChatSession(sessionId)
    sessions.value = sessions.value.filter((session) => session.sessionId !== sessionId)
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = ''
      messages.value = []
      citations.value = []
    }
  }

  function clearChat(): void {
    activeSessionId.value = ''
    messages.value = []
    citations.value = []
    errorMessage.value = ''
  }

  return {
    messages,
    citations,
    sessions,
    recentChats,
    activeSessionId,
    selectedContextFileIds,
    enableDeepThinking,
    breadcrumbs,
    isAnswering,
    errorMessage,
    setContextFileIds,
    toggleDeepThinking,
    loadSessions,
    startNewChat,
    openSession,
    renameSession,
    toggleSessionPinned,
    deleteSession,
    sendQuestion,
    clearChat,
  }
}

function toMessagesFromTurn(turn: PdfChatTurn): PdfChatMessage[] {
  return [
    {
      id: `${turn.turnId}-user`,
      role: 'user',
      content: turn.question,
    },
    toAssistantMessage(turn.answer, `${turn.turnId}-assistant`),
  ]
}

function toAssistantMessage(answer: PdfChatAnswer, id = newMessageId('assistant')): PdfChatMessage {
  const content = answer.answerBlocks
    .map((block) => block.text.trim())
    .filter(Boolean)
    .join('\n\n')
  return {
    id,
    role: 'assistant',
    content: content || 'No answer text was generated.',
    reasoning: answer.answerBlocks
      .map((block) => block.reasoning.trim())
      .filter(Boolean)
      .join('\n\n'),
    citationIds: answer.citations.map((citation) => citation.citationId),
    insufficientEvidence: answer.insufficientEvidence,
  }
}

function toSourceCitations(answer: PdfChatAnswer): PdfCitation[] {
  return answer.citations.map((citation, index) => ({
    id: citation.citationId,
    sourceLabel: citation.citationId,
    fileName: citation.fileName,
    fileKind: 'pdf',
    matchLabel: citation.pageLabel ?? `Chunk ${citation.chunkIndex + 1}`,
    excerpt: citation.quote,
    location: [
      citation.pageLabel,
      citation.title,
      `Chunk ${citation.chunkIndex + 1}`,
    ].filter(Boolean).join(' - '),
    tone: index === 0 ? 'primary' : 'supporting',
  }))
}

function newMessageId(prefix: 'assistant' | 'user'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function dedupeFileIds(fileIds: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const fileId of fileIds) {
    const normalized = fileId.trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    result.push(normalized)
  }
  return result
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF chat request failed.'
}
