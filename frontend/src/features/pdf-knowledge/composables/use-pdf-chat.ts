import { computed, ref } from 'vue'

import { answerPdfQuestion } from '../../../api/pdf-knowledge-api'
import type { PdfChatAnswer, PdfChatMessage, PdfCitation } from '../types'

const defaultRetrievalLimit = 8

export function usePdfChat() {
  const messages = ref<PdfChatMessage[]>([])
  const citations = ref<PdfCitation[]>([])
  const isAnswering = ref(false)
  const errorMessage = ref('')

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
      const answer = await answerPdfQuestion({
        question: normalizedQuestion,
        retrievalLimit: defaultRetrievalLimit,
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

  function clearChat(): void {
    messages.value = []
    citations.value = []
    errorMessage.value = ''
  }

  return {
    messages,
    citations,
    breadcrumbs,
    isAnswering,
    errorMessage,
    sendQuestion,
    clearChat,
  }
}

function toAssistantMessage(answer: PdfChatAnswer): PdfChatMessage {
  const content = answer.answerBlocks
    .map((block) => block.text.trim())
    .filter(Boolean)
    .join('\n\n')
  return {
    id: newMessageId('assistant'),
    role: 'assistant',
    content: content || 'No answer text was generated.',
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

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF chat request failed.'
}
