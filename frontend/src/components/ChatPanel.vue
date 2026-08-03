<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import {
  askExcelQuestion,
  cancelChatRequest,
  createChatSession,
  listChatSessionTurns,
} from '../api/chat-api'
import type { ChatAnswer, ChatSession, ExcelCitation, SelectedDocument } from '../types/chat'
import { renderMarkdown } from '../utils/markdown'
import AppIcon from './AppIcon.vue'

interface ChatHistoryEntry {
  id: string
  question: string
  answer: ChatAnswer | null
  createdAt: string
}

interface PendingHistoryEntry {
  sessionKey: string
  entryId: string
}

interface RenderedAnswerBlock {
  body: string
  thinking: string
}

const draftSessionKey = '__draft__'
const renderedBlockCacheLimit = 180
const cachedSessionHistoryLimit = 8
const cachedEntriesPerSessionLimit = 120

const props = defineProps<{
  routerProvider: string | null
  routerModel: string | null
  answerProvider: string | null
  answerModel: string | null
  answerSupportsDeepThinking: boolean
  sessionId: string
  sessionTitle: string
  documentTitles: Record<string, string>
  activeDocument: SelectedDocument | null
}>()

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  askingStateChanged: [isAsking: boolean]
  collapse: []
  selectCitation: [citation: ExcelCitation]
  selectDocument: [document: SelectedDocument]
  sessionCreated: [session: ChatSession]
  sessionTitleSuggested: [sessionId: string, title: string]
}>()

const question = ref<string>('')
const historiesBySession = ref<Record<string, ChatHistoryEntry[]>>({})
const errorMessage = ref<string>('')
const isAsking = ref<boolean>(false)
const isHistoryLoading = ref<boolean>(false)
const enableDeepThinking = ref<boolean>(false)
const activeChatRequestId = ref<string>('')
const copiedKey = ref<string>('')
const chatScrollRegion = ref<HTMLElement | null>(null)
const chatInput = ref<HTMLTextAreaElement | null>(null)
const activeSourceIndex = ref<number>(0)
let nextHistoryEntryId = 0
let historyLoadRequestId = 0
let activeChatAbortController: AbortController | null = null
let activePendingEntry: PendingHistoryEntry | null = null
let copiedKeyTimer: number | null = null
const renderedBlockCache = new Map<string, RenderedAnswerBlock>()

const currentSessionKey = computed(() => props.sessionId || draftSessionKey)
const effectiveDeepThinkingEnabled = computed(
  () => enableDeepThinking.value && props.answerSupportsDeepThinking,
)
const deepThinkingTitle = computed(() => {
  if (!props.answerSupportsDeepThinking) {
    return 'Deep thinking is not available for the selected answer model'
  }
  return enableDeepThinking.value
    ? 'Deep thinking on: the model may spend more time reasoning through evidence'
    : 'Deep thinking off'
})
const deepThinkingAriaLabel = computed(() => {
  if (!props.answerSupportsDeepThinking) {
    return 'Deep thinking unavailable for selected answer model'
  }
  return enableDeepThinking.value ? 'Disable deep thinking' : 'Enable deep thinking'
})

const history = computed<ChatHistoryEntry[]>(() => {
  return historiesBySession.value[currentSessionKey.value] ?? []
})

const latestAnswer = computed<ChatAnswer | null>(() => {
  for (let index = history.value.length - 1; index >= 0; index -= 1) {
    const answer = history.value[index]?.answer
    if (answer) {
      return answer
    }
  }
  return null
})

const activeSourceDocuments = computed<SelectedDocument[]>(() => {
  return latestAnswer.value?.selected_documents ?? []
})

const dataSourceDocuments = computed<SelectedDocument[]>(() => {
  return activeSourceDocuments.value
})

const activeDataSourceDocument = computed<SelectedDocument | null>(() => {
  return dataSourceDocuments.value[normalizedSourceIndex.value] ?? null
})

const normalizedSourceIndex = computed(() => {
  const count = dataSourceDocuments.value.length
  if (count === 0) {
    return 0
  }
  return Math.min(activeSourceIndex.value, count - 1)
})

const sourceCountLabel = computed(() => {
  const count = dataSourceDocuments.value.length
  return `${count} ${count === 1 ? 'Document' : 'Documents'}`
})

const sourcePositionLabel = computed(() => {
  const count = dataSourceDocuments.value.length
  if (count <= 1) {
    return ''
  }
  return `${normalizedSourceIndex.value + 1}/${count}`
})

watch(currentSessionKey, () => {
  void loadSessionHistory()
  void scrollChatToBottom()
}, { immediate: true })

watch(
  () => [history.value.length, history.value.at(-1)?.answer?.created_at, errorMessage.value],
  () => {
    void scrollChatToBottom()
  },
  { flush: 'post' },
)

watch(question, () => {
  void nextTick(resizeChatInput)
})

watch(
  () => dataSourceDocuments.value.map(documentKey).join('|'),
  () => {
    activeSourceIndex.value = 0
  },
)

watch(
  () => props.answerSupportsDeepThinking,
  (supported) => {
    if (!supported) {
      enableDeepThinking.value = false
    }
  },
  { immediate: true },
)

watch(
  isAsking,
  (value) => {
    emit('askingStateChanged', value)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (activeChatRequestId.value) {
    void cancelChatRequest(activeChatRequestId.value).catch(() => undefined)
  }
  activeChatAbortController?.abort()
  activeChatAbortController = null
  clearCopiedTimer()
})

async function scrollChatToBottom(): Promise<void> {
  await nextTick()
  const element = chatScrollRegion.value
  if (element) {
    element.scrollTop = element.scrollHeight
  }
}

async function loadSessionHistory(): Promise<void> {
  const sessionId = props.sessionId
  const requestId = ++historyLoadRequestId
  if (!sessionId) {
    isHistoryLoading.value = false
    errorMessage.value = ''
    setHistory(draftSessionKey, historyForSession(draftSessionKey))
    return
  }
  if (
    isAsking.value
    && activePendingEntry?.sessionKey === sessionId
    && historyForSession(sessionId).some((entry) => entry.answer === null)
  ) {
    isHistoryLoading.value = false
    return
  }
  isHistoryLoading.value = true
  errorMessage.value = ''
  try {
    const turns = await listChatSessionTurns(sessionId)
    if (requestId !== historyLoadRequestId) {
      return
    }
    setHistory(
      sessionId,
      turns.map((turn) => ({
        id: turn.turn_id,
        question: turn.question,
        answer: turn.answer,
        createdAt: turn.created_at,
      })),
    )
    await scrollChatToBottom()
  } catch (error: unknown) {
    if (requestId === historyLoadRequestId) {
      errorMessage.value = error instanceof Error ? error.message : 'Failed to load chat history.'
    }
  } finally {
    if (requestId === historyLoadRequestId) {
      isHistoryLoading.value = false
    }
  }
}

async function submitQuestion(): Promise<void> {
  const trimmedQuestion = question.value.trim()
  if (!trimmedQuestion) {
    errorMessage.value = 'Enter a question first.'
    return
  }
  if (isAsking.value) {
    return
  }

  errorMessage.value = ''
  isAsking.value = true
  const requestId = newChatRequestId()
  const abortController = new AbortController()
  activeChatRequestId.value = requestId
  activeChatAbortController = abortController

  let targetSessionId = props.sessionId
  let targetSessionKey = props.sessionId || draftSessionKey
  let entry: ChatHistoryEntry | null = null
  let createdSession = false

  try {
    question.value = ''
    await nextTick()
    resizeChatInput()

    if (!targetSessionId) {
      const session = await createChatSession()
      if (activeChatRequestId.value !== requestId) {
        return
      }
      targetSessionId = session.session_id
      targetSessionKey = session.session_id
      createdSession = true
      emit('sessionCreated', session)
    }

    const entryId = `pending-${Date.now()}-${++nextHistoryEntryId}`
    entry = {
      id: entryId,
      question: trimmedQuestion,
      answer: null,
      createdAt: new Date().toISOString(),
    }
    setHistory(targetSessionKey, [...historyForSession(targetSessionKey), entry])
    activePendingEntry = { sessionKey: targetSessionKey, entryId }
    await scrollChatToBottom()

    const answer = await askExcelQuestion(
      trimmedQuestion,
      targetSessionId,
      {
        enableDeepThinking: effectiveDeepThinkingEnabled.value,
      },
      {
        requestId,
        signal: abortController.signal,
      },
    )
    if (activeChatRequestId.value !== requestId) {
      return
    }
    setHistory(
      targetSessionKey,
      historyForSession(targetSessionKey).map((item) => (
        item.id === entryId ? { ...item, answer } : item
      )),
    )
    activePendingEntry = null
    emit('answerReceived', answer)
    await scrollChatToBottom()

    if (createdSession || !props.sessionTitle || props.sessionTitle === 'New chat') {
      emit('sessionTitleSuggested', answer.session_id, titleFromQuestion(trimmedQuestion))
    }

  } catch (error: unknown) {
    if (entry) {
      if (activeChatRequestId.value === requestId) {
        removeHistoryEntry({ sessionKey: targetSessionKey, entryId: entry.id })
      }
    }
    if (isAbortError(error) || activeChatRequestId.value !== requestId) {
      return
    }
    errorMessage.value = error instanceof Error ? error.message : 'Unexpected error.'
    await scrollChatToBottom()
  } finally {
    if (activeChatRequestId.value === requestId) {
      activeChatRequestId.value = ''
      activeChatAbortController = null
      isAsking.value = false
    }
  }
}

async function stopCurrentAnswer(): Promise<void> {
  const requestId = activeChatRequestId.value
  if (!requestId) {
    return
  }
  const pendingEntry = activePendingEntry
  const restoredQuestion = pendingEntry
    ? historyForSession(pendingEntry.sessionKey).find(
      (entry) => entry.id === pendingEntry.entryId,
    )?.question
    : ''
  const cancelPromise = cancelChatRequest(requestId).catch(() => undefined)
  activeChatRequestId.value = ''
  activeChatAbortController?.abort()
  activeChatAbortController = null
  isAsking.value = false
  if (pendingEntry) {
    if (restoredQuestion) {
      question.value = restoredQuestion
    }
    activePendingEntry = null
    await nextTick()
    resizeChatInput()
    chatInput.value?.focus()
  }
  errorMessage.value = ''
  await scrollChatToBottom()
  await cancelPromise
}

function removeHistoryEntry(entry: PendingHistoryEntry): void {
  setHistory(
    entry.sessionKey,
    historyForSession(entry.sessionKey).filter((item) => item.id !== entry.entryId),
  )
  if (activePendingEntry?.entryId === entry.entryId) {
    activePendingEntry = null
  }
}

async function regenerateLatestAnswer(): Promise<void> {
  const lastEntry = latestCompleteEntry()
  if (!lastEntry || isAsking.value) {
    return
  }
  await submitQuestionText(lastEntry.question)
}

async function editLatestQuestion(): Promise<void> {
  const lastEntry = latestCompleteEntry()
  if (!lastEntry || isAsking.value) {
    return
  }
  question.value = lastEntry.question
  await nextTick()
  resizeChatInput()
  chatInput.value?.focus()
}

async function submitQuestionText(value: string): Promise<void> {
  question.value = value
  await nextTick()
  await submitQuestion()
}

function latestCompleteEntry(): ChatHistoryEntry | null {
  for (let index = history.value.length - 1; index >= 0; index -= 1) {
    const entry = history.value[index]
    if (entry?.answer) {
      return entry
    }
  }
  return null
}

function newChatRequestId(): string {
  const randomPart = window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  return `chat-${randomPart}`
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && (
    error.name === 'AbortError' ||
    error.message === 'Chat request cancelled.'
  )
}

function historyForSession(sessionKey: string): ChatHistoryEntry[] {
  return historiesBySession.value[sessionKey] ?? []
}

function setHistory(sessionKey: string, entries: ChatHistoryEntry[]): void {
  const nextHistories = {
    ...historiesBySession.value,
    [sessionKey]: trimHistoryEntries(entries),
  }
  historiesBySession.value = trimHistorySessionCache(nextHistories, sessionKey)
}

function trimHistoryEntries(entries: ChatHistoryEntry[]): ChatHistoryEntry[] {
  if (entries.length <= cachedEntriesPerSessionLimit) {
    return entries
  }
  return entries.slice(-cachedEntriesPerSessionLimit)
}

function trimHistorySessionCache(
  histories: Record<string, ChatHistoryEntry[]>,
  preferredSessionKey: string,
): Record<string, ChatHistoryEntry[]> {
  const keys = Object.keys(histories)
  if (keys.length <= cachedSessionHistoryLimit) {
    return histories
  }

  const keepKeys = new Set([preferredSessionKey, currentSessionKey.value, draftSessionKey])
  const rankedKeys = keys.sort((left, right) => (
    latestHistoryTimestamp(histories[right]) - latestHistoryTimestamp(histories[left])
  ))
  const retainedKeys = new Set<string>()
  for (const key of rankedKeys) {
    if (retainedKeys.size < cachedSessionHistoryLimit || keepKeys.has(key)) {
      retainedKeys.add(key)
    }
  }
  for (const key of [...rankedKeys].reverse()) {
    if (retainedKeys.size <= cachedSessionHistoryLimit) {
      break
    }
    if (!keepKeys.has(key)) {
      retainedKeys.delete(key)
    }
  }

  return Object.fromEntries(
    Object.entries(histories).filter(([key]) => retainedKeys.has(key)),
  )
}

function latestHistoryTimestamp(entries: ChatHistoryEntry[] | undefined): number {
  const value = entries?.at(-1)?.createdAt
  if (!value) {
    return 0
  }
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function selectCitationById(answer: ChatAnswer, citationId: string): void {
  const citation = answer.citations.find((item) => item.citation_id === citationId)
  if (citation) {
    emit('selectCitation', citation)
  }
}

function renderAnswerBlock(markdown: string, reasoning = ''): RenderedAnswerBlock {
  const cacheKey = `${reasoning}\n\x00\n${markdown}`
  const cached = renderedBlockCache.get(cacheKey)
  if (cached) {
    renderedBlockCache.delete(cacheKey)
    renderedBlockCache.set(cacheKey, cached)
    return cached
  }
  const rendered = splitThinkingFromAnswer(markdown)
  if (reasoning.trim()) {
    rendered.thinking = [reasoning.trim(), rendered.thinking].filter(Boolean).join('\n\n')
  }
  renderedBlockCache.set(cacheKey, rendered)
  trimRenderedBlockCache()
  return rendered
}

function trimRenderedBlockCache(): void {
  while (renderedBlockCache.size > renderedBlockCacheLimit) {
    const oldestKey = renderedBlockCache.keys().next().value
    if (typeof oldestKey !== 'string') {
      return
    }
    renderedBlockCache.delete(oldestKey)
  }
}

function splitThinkingFromAnswer(value: string): RenderedAnswerBlock {
  let remaining = value.replace(/\r\n?/g, '\n').trim()
  const thinkingParts: string[] = []
  const taggedThinkingPattern = /<(?:think|thinking|reasoning)>\s*([\s\S]*?)\s*<\/(?:think|thinking|reasoning)>/gi
  remaining = remaining.replace(taggedThinkingPattern, (_match, thinking: string) => {
    if (thinking.trim()) {
      thinkingParts.push(thinking.trim())
    }
    return '\n'
  }).trim()

  const labeledMatch = /^(?:思考过程|思考|推理过程|Reasoning|Thinking)\s*[:：]\s*([\s\S]*?)(?:\n{2,}(?:正文|答案|Answer)\s*[:：]\s*|\n{2,}(?=#+\s)|$)([\s\S]*)$/i.exec(remaining)
  if (labeledMatch) {
    const thinking = labeledMatch[1]?.trim() ?? ''
    const body = labeledMatch[2]?.trim() ?? ''
    if (thinking) {
      thinkingParts.push(thinking)
    }
    remaining = body || remaining
  }

  return {
    thinking: thinkingParts.join('\n\n'),
    body: remaining.trim(),
  }
}

function answerPlainText(answer: ChatAnswer): string {
  return answer.answer_blocks
    .map((block) => block.text.trim())
    .filter(Boolean)
    .join('\n\n')
}

async function copyText(value: string, key: string): Promise<void> {
  if (!value.trim()) {
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      copyTextWithTextareaFallback(value)
    }
    showCopied(key)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Failed to copy text.'
  }
}

function copyTextWithTextareaFallback(value: string): void {
  const textArea = document.createElement('textarea')
  textArea.value = value
  textArea.setAttribute('readonly', 'true')
  textArea.style.position = 'fixed'
  textArea.style.left = '-9999px'
  document.body.appendChild(textArea)
  textArea.select()
  document.execCommand('copy')
  textArea.remove()
}

function showCopied(key: string): void {
  copiedKey.value = key
  clearCopiedTimer()
  copiedKeyTimer = window.setTimeout(() => {
    copiedKey.value = ''
    copiedKeyTimer = null
  }, 1600)
}

function clearCopiedTimer(): void {
  if (copiedKeyTimer !== null) {
    window.clearTimeout(copiedKeyTimer)
    copiedKeyTimer = null
  }
}

function selectDocument(document: SelectedDocument): void {
  emit('selectDocument', document)
}

function stepDataSource(direction: -1 | 1): void {
  const count = dataSourceDocuments.value.length
  if (count <= 1) {
    return
  }
  activeSourceIndex.value = (normalizedSourceIndex.value + direction + count) % count
}

function titleFromQuestion(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length > 56 ? `${normalized.slice(0, 53)}...` : normalized
}

function documentKey(document: SelectedDocument): string {
  return `${document.file_id}-${document.version_id}`
}

function documentTitle(document: SelectedDocument): string {
  return props.documentTitles[document.file_id] ?? shortId(document.file_id)
}

function shortId(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function formatMessageTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date).toUpperCase()
}

function handleDraftInput(): void {
  resizeChatInput()
}

function handleDraftKeydown(event: KeyboardEvent): void {
  if (event.isComposing) {
    return
  }
  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }
  event.preventDefault()
  void submitQuestion()
}

function resizeChatInput(): void {
  const element = chatInput.value
  if (!element) {
    return
  }
  element.style.height = '0px'
  element.style.height = `${Math.min(element.scrollHeight, 140)}px`
}
</script>

<template>
  <section class="chat-panel" aria-label="Chat and citations">
    <header class="chat-panel-head">
      <h3>Chat &amp; Citations</h3>
      <button
        type="button"
        class="chat-icon-button"
        aria-label="Collapse chat panel"
        title="Collapse chat panel"
        @click="emit('collapse')"
      >
        <AppIcon name="close_fullscreen" />
      </button>
    </header>

    <div ref="chatScrollRegion" class="chat-scroll-region custom-scrollbar">
      <section class="chat-data-sources-card" aria-label="Data sources for current turn">
        <div class="chat-data-sources-head">
          <div>
            <span>Data Sources</span>
            <strong>{{ sourceCountLabel }}</strong>
          </div>
          <button type="button" class="chat-source-menu" aria-label="Data source options">
            <AppIcon name="more_vert" />
          </button>
        </div>
        <div class="chat-data-source-list">
          <button
            v-if="activeDataSourceDocument"
            :key="documentKey(activeDataSourceDocument)"
            type="button"
            class="chat-data-source-row"
            @click="selectDocument(activeDataSourceDocument)"
          >
            <span class="chat-source-file-icon">
              <AppIcon name="description" />
            </span>
            <span class="chat-source-copy">
              <strong :title="documentTitle(activeDataSourceDocument)">
                {{ documentTitle(activeDataSourceDocument) }}
              </strong>
              <span>Active Source</span>
            </span>
            <span class="chat-source-status" aria-hidden="true">
              <span></span>
            </span>
            <span class="chat-source-pager" @click.stop>
              <small v-if="sourcePositionLabel">{{ sourcePositionLabel }}</small>
              <button
                type="button"
                aria-label="Previous data source"
                :disabled="dataSourceDocuments.length <= 1"
                @click="stepDataSource(-1)"
              >
                <AppIcon name="keyboard_arrow_up" />
              </button>
              <button
                type="button"
                aria-label="Next data source"
                :disabled="dataSourceDocuments.length <= 1"
                @click="stepDataSource(1)"
              >
                <AppIcon name="keyboard_arrow_down" />
              </button>
            </span>
          </button>
          <div v-else class="chat-data-source-empty">
            <span class="chat-source-file-icon muted">
              <AppIcon name="description" />
            </span>
            <span class="chat-source-copy">
              <strong>No active source</strong>
              <span>Select or ask about a document</span>
            </span>
            <span class="chat-source-pager disabled" aria-hidden="true">
              <button type="button" disabled>
                <AppIcon name="keyboard_arrow_up" />
              </button>
              <button type="button" disabled>
                <AppIcon name="keyboard_arrow_down" />
              </button>
            </span>
          </div>
        </div>
      </section>

      <div class="chat-history">
        <template v-for="(entry, entryIndex) in history" :key="entry.id">
          <div class="chat-message user">
            <div class="user-message-stack">
              <div class="user-bubble">{{ entry.question }}</div>
              <div class="message-actions user-actions">
                <button
                  type="button"
                  class="message-action-button"
                  :aria-label="copiedKey === `question-${entry.id}` ? 'Question copied' : 'Copy question'"
                  :title="copiedKey === `question-${entry.id}` ? 'Copied' : 'Copy question'"
                  @click="copyText(entry.question, `question-${entry.id}`)"
                >
                  <AppIcon :name="copiedKey === `question-${entry.id}` ? 'check' : 'content_copy'" />
                  <span>{{ copiedKey === `question-${entry.id}` ? 'Copied' : 'Copy' }}</span>
                </button>
                <button
                  v-if="entry.answer && entry.id === latestCompleteEntry()?.id"
                  type="button"
                  class="message-action-button"
                  :disabled="isAsking"
                  aria-label="Edit latest question"
                  title="Edit latest question"
                  @click="editLatestQuestion"
                >
                  <AppIcon name="edit" />
                  <span>Edit</span>
                </button>
              </div>
            </div>
            <span class="chat-message-time">{{ formatMessageTime(entry.createdAt) }}</span>
          </div>

          <article v-if="entry.answer" class="chat-message assistant">
            <div class="assistant-message-stack">
              <div class="assistant-title">
                <span class="assistant-bot-icon">
                  <AppIcon name="analytics" />
                </span>
                <strong>ExcelAI</strong>
              </div>
              <div class="assistant-bubble">
                <p v-if="entry.answer.insufficient_evidence" class="warning-text">
                  Insufficient evidence.
                </p>
                <div
                  v-for="(block, blockIndex) in entry.answer.answer_blocks"
                  :key="`${entry.answer.created_at}-${blockIndex}`"
                  class="answer-block"
                >
                  <details
                    v-if="renderAnswerBlock(block.text, block.reasoning).thinking"
                    class="thinking-details"
                  >
                    <summary>
                      <AppIcon name="psychology" />
                      <span>Model reasoning</span>
                    </summary>
                    <div
                      class="markdown-body thinking-markdown"
                      v-html="renderMarkdown(renderAnswerBlock(block.text, block.reasoning).thinking)"
                    ></div>
                  </details>
                  <div
                    v-if="renderAnswerBlock(block.text, block.reasoning).body"
                    class="markdown-body"
                    v-html="renderMarkdown(renderAnswerBlock(block.text, block.reasoning).body)"
                  ></div>
                  <div v-if="block.citation_ids.length > 0" class="answer-block-citations">
                    <button
                      v-for="citationId in block.citation_ids"
                      :key="`${entry.answer.created_at}-${blockIndex}-${citationId}`"
                      type="button"
                      class="citation-chip"
                      :aria-label="`Open citation ${citationId}`"
                      @click="selectCitationById(entry.answer, citationId)"
                    >
                      [{{ citationId }}]
                    </button>
                  </div>
                </div>
                <p v-if="entry.answer.answer_blocks.length === 0" class="empty-copy">
                  No answer blocks returned.
                </p>
                <div v-if="entry.answer.warnings.length > 0" class="warning-list">
                  <p v-for="warning in entry.answer.warnings" :key="warning">{{ warning }}</p>
                </div>
                <div class="message-actions assistant-actions">
                  <button
                    type="button"
                    class="message-action-button"
                    :aria-label="copiedKey === `answer-${entry.id}` ? 'Answer copied' : 'Copy answer'"
                    :title="copiedKey === `answer-${entry.id}` ? 'Copied' : 'Copy answer'"
                    @click="copyText(answerPlainText(entry.answer), `answer-${entry.id}`)"
                  >
                    <AppIcon :name="copiedKey === `answer-${entry.id}` ? 'check' : 'content_copy'" />
                    <span>{{ copiedKey === `answer-${entry.id}` ? 'Copied' : 'Copy' }}</span>
                  </button>
                  <button
                    v-if="entry.id === latestCompleteEntry()?.id"
                    type="button"
                    class="message-action-button"
                    :disabled="isAsking"
                    aria-label="Regenerate latest answer"
                    title="Regenerate latest answer"
                    @click="regenerateLatestAnswer"
                  >
                    <AppIcon name="refresh" />
                    <span>Regenerate</span>
                  </button>
                </div>
              </div>
            </div>
            <span class="chat-message-time">
              {{ formatMessageTime(entry.answer.created_at || entry.createdAt) }}
            </span>
          </article>

          <article
            v-else-if="isAsking && entryIndex === history.length - 1"
            class="chat-message assistant"
          >
            <div class="assistant-message-stack">
              <div class="assistant-title thinking-title">
                <span class="assistant-bot-icon">
                  <AppIcon name="analytics" />
                </span>
                <strong>Thinking...</strong>
              </div>
              <div class="assistant-bubble loading-message" aria-live="polite" aria-busy="true">
                <div class="loading-bars" aria-hidden="true">
                  <span></span>
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <div class="thinking-copy">
                  <strong>{{ effectiveDeepThinkingEnabled ? 'Deep reasoning' : 'Tracing evidence' }}</strong>
                  <span>{{ effectiveDeepThinkingEnabled ? 'Routing files. Checking evidence. Composing.' : 'Routing files. Reading rows. Composing.' }}</span>
                </div>
              </div>
            </div>
          </article>
        </template>

        <p v-if="errorMessage" class="chat-error-note">{{ errorMessage }}</p>
        <p v-else-if="isHistoryLoading" class="chat-loading-note">Loading chat history...</p>
      </div>
    </div>

    <form class="chat-input-card" @submit.prevent="submitQuestion">
      <div class="chat-input-shell">
        <textarea
          ref="chatInput"
          v-model="question"
          rows="1"
          placeholder="Ask about your data..."
          @input="handleDraftInput"
          @keydown="handleDraftKeydown"
        />
        <div class="chat-input-actions">
          <div class="chat-tools">
            <button
              type="button"
              class="chat-tool-button thinking-toggle"
              :class="{ active: enableDeepThinking, unavailable: !answerSupportsDeepThinking }"
              :aria-pressed="enableDeepThinking"
              :aria-label="deepThinkingAriaLabel"
              :title="deepThinkingTitle"
              :disabled="isAsking || !answerSupportsDeepThinking"
              @click="enableDeepThinking = !enableDeepThinking"
            >
              <AppIcon name="psychology" />
              <span>Deep Think</span>
            </button>
          </div>
          <button
            v-if="!isAsking"
            type="submit"
            class="chat-send-button"
            :disabled="!question.trim()"
            aria-label="Send message"
          >
            <AppIcon name="arrow_upward" />
          </button>
          <button
            v-else
            type="button"
            class="chat-send-button stop"
            aria-label="Stop generating"
            title="Stop generating"
            @click="stopCurrentAnswer"
          >
            <AppIcon name="stop" />
          </button>
        </div>
      </div>
      <p class="chat-disclaimer">
        AI may produce inaccurate results. Always verify.
      </p>
    </form>
  </section>
</template>
