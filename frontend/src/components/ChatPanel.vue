<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import {
  askExcelQuestion,
  createChatSession,
} from '../api/chat-api'
import type { ChatAnswer, ChatSession, ExcelCitation, SelectedDocument } from '../types/chat'
import AppIcon from './AppIcon.vue'

interface ChatHistoryEntry {
  id: string
  question: string
  answer: ChatAnswer | null
  createdAt: string
}

const draftSessionKey = '__draft__'

const props = defineProps<{
  routerProvider: string | null
  routerModel: string | null
  answerProvider: string | null
  answerModel: string | null
  sessionId: string
  sessionTitle: string
  documentTitles: Record<string, string>
  activeDocument: SelectedDocument | null
}>()

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  selectCitation: [citation: ExcelCitation]
  selectDocument: [document: SelectedDocument]
  sessionCreated: [session: ChatSession]
  sessionTitleSuggested: [sessionId: string, title: string]
}>()

const question = ref<string>('')
const historiesBySession = ref<Record<string, ChatHistoryEntry[]>>({})
const errorMessage = ref<string>('')
const isAsking = ref<boolean>(false)
const chatScrollRegion = ref<HTMLElement | null>(null)
const chatInput = ref<HTMLTextAreaElement | null>(null)
const activeSourceIndex = ref<number>(0)
let nextHistoryEntryId = 0

const currentSessionKey = computed(() => props.sessionId || draftSessionKey)

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
  return `${count} ${count === 1 ? 'File' : 'Files'}`
})

const sourcePositionLabel = computed(() => {
  const count = dataSourceDocuments.value.length
  if (count <= 1) {
    return ''
  }
  return `${normalizedSourceIndex.value + 1}/${count}`
})

watch(currentSessionKey, () => {
  void scrollChatToBottom()
})

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

async function scrollChatToBottom(): Promise<void> {
  await nextTick()
  const element = chatScrollRegion.value
  if (element) {
    element.scrollTop = element.scrollHeight
  }
}

async function submitQuestion(): Promise<void> {
  const trimmedQuestion = question.value.trim()
  if (!trimmedQuestion) {
    errorMessage.value = 'Enter a question first.'
    return
  }

  errorMessage.value = ''
  isAsking.value = true

  let targetSessionId = props.sessionId
  let targetSessionKey = props.sessionId || draftSessionKey
  let entry: ChatHistoryEntry | null = null
  let createdSession = false

  try {
    if (!targetSessionId) {
      const session = await createChatSession()
      targetSessionId = session.session_id
      targetSessionKey = session.session_id
      createdSession = true
      emit('sessionCreated', session)
    }

    const entryId = `entry-${++nextHistoryEntryId}`
    entry = {
      id: entryId,
      question: trimmedQuestion,
      answer: null,
      createdAt: new Date().toISOString(),
    }
    setHistory(targetSessionKey, [...historyForSession(targetSessionKey), entry])
    await scrollChatToBottom()

    const answer = await askExcelQuestion(
      trimmedQuestion,
      targetSessionId,
      {
        routerProvider: props.routerProvider ?? '',
        routerModel: props.routerModel ?? '',
        answerProvider: props.answerProvider ?? '',
        answerModel: props.answerModel ?? '',
      },
    )
    setHistory(
      targetSessionKey,
      historyForSession(targetSessionKey).map((item) => (
        item.id === entryId ? { ...item, answer } : item
      )),
    )
    emit('answerReceived', answer)
    await scrollChatToBottom()

    if (createdSession || !props.sessionTitle || props.sessionTitle === 'New chat') {
      emit('sessionTitleSuggested', answer.session_id, titleFromQuestion(trimmedQuestion))
    }

    question.value = ''
    await nextTick()
    resizeChatInput()
  } catch (error: unknown) {
    if (entry) {
      const failedEntry = entry
      setHistory(
        targetSessionKey,
        historyForSession(targetSessionKey).filter((item) => item.id !== failedEntry.id),
      )
    }
    errorMessage.value = error instanceof Error ? error.message : 'Unexpected error.'
    await scrollChatToBottom()
  } finally {
    isAsking.value = false
  }
}

function historyForSession(sessionKey: string): ChatHistoryEntry[] {
  return historiesBySession.value[sessionKey] ?? []
}

function setHistory(sessionKey: string, entries: ChatHistoryEntry[]): void {
  historiesBySession.value = {
    ...historiesBySession.value,
    [sessionKey]: entries,
  }
}

function selectCitationById(answer: ChatAnswer, citationId: string): void {
  const citation = answer.citations.find((item) => item.citation_id === citationId)
  if (citation) {
    emit('selectCitation', citation)
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
      <button type="button" class="chat-icon-button" aria-label="Collapse chat panel">
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
              <span>Select or ask about a workbook</span>
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
            <div class="user-bubble">{{ entry.question }}</div>
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
                  <p>{{ block.text }}</p>
                  <button
                    v-for="citationId in block.citation_ids"
                    :key="`${entry.answer.created_at}-${blockIndex}-${citationId}`"
                    type="button"
                    class="citation-chip"
                    @click="selectCitationById(entry.answer, citationId)"
                  >
                    [{{ citationId }}]
                  </button>
                </div>
                <p v-if="entry.answer.answer_blocks.length === 0" class="empty-copy">
                  No answer blocks returned.
                </p>
                <div v-if="entry.answer.warnings.length > 0" class="warning-list">
                  <p v-for="warning in entry.answer.warnings" :key="warning">{{ warning }}</p>
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
              <div class="assistant-title">
                <span class="assistant-bot-icon">
                  <AppIcon name="analytics" />
                </span>
                <strong>ExcelAI</strong>
              </div>
              <div class="assistant-bubble loading-message">
                Waiting for model response.
              </div>
            </div>
          </article>
        </template>

        <p v-if="errorMessage" class="chat-error-note">{{ errorMessage }}</p>
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
          @keydown.meta.enter="submitQuestion"
          @keydown.ctrl.enter="submitQuestion"
        />
        <div class="chat-input-actions">
          <div class="chat-tools">
            <button type="button" class="chat-tool-button" aria-label="Attach file">
              <AppIcon name="attach_file" />
            </button>
            <button type="button" class="chat-tool-button" aria-label="Add chart">
              <AppIcon name="add_chart" />
            </button>
          </div>
          <button
            type="submit"
            class="chat-send-button"
            :disabled="isAsking || !question.trim()"
            aria-label="Send message"
          >
            <AppIcon :name="isAsking ? 'history' : 'arrow_upward'" />
          </button>
        </div>
      </div>
      <p class="chat-disclaimer">
        AI may produce inaccurate financial results. Always verify.
      </p>
    </form>
  </section>
</template>
