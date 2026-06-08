<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import {
  askExcelQuestion,
  createChatSession,
} from '../api/chat-api'
import type { ChatAnswer, ChatSession, ExcelCitation } from '../types/chat'
import SourceTracePanel from './SourceTracePanel.vue'

interface ChatHistoryEntry {
  id: string
  question: string
  answer: ChatAnswer | null
}

const draftSessionKey = '__draft__'

const props = defineProps<{
  routerProvider: string | null
  routerModel: string | null
  answerProvider: string | null
  answerModel: string | null
  sessionId: string
  sessionTitle: string
}>()

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  selectCitation: [citation: ExcelCitation]
  sessionCreated: [session: ChatSession]
  sessionTitleSuggested: [sessionId: string, title: string]
}>()

const question = ref<string>('')
const historiesBySession = ref<Record<string, ChatHistoryEntry[]>>({})
const selectedCitation = ref<ExcelCitation | null>(null)
const errorMessage = ref<string>('')
const isAsking = ref<boolean>(false)
const isTimingExpanded = ref<boolean>(false)
const chatScrollRegion = ref<HTMLElement | null>(null)
let nextHistoryEntryId = 0

const currentSessionKey = computed(() => props.sessionId || draftSessionKey)

const history = computed<ChatHistoryEntry[]>(() => {
  return historiesBySession.value[currentSessionKey.value] ?? []
})

const currentSessionLabel = computed(() => {
  return props.sessionTitle || 'New chat'
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

const latestEntry = computed<ChatHistoryEntry | null>(() => {
  return history.value.at(-1) ?? null
})

const latestTimings = computed(() => {
  return latestEntry.value ? entryTimings(latestEntry.value) : []
})

const latestTotalSeconds = computed(() => {
  const timings = latestTimings.value
  return (
    timingValue(timings, 'chat_total') ||
    timingValue(timings, 'answer_total') ||
    timingValue(timings, 'route_total')
  )
})

const timingToggleLabel = computed(() => {
  return isTimingExpanded.value ? 'Hide' : 'Show'
})

watch(currentSessionKey, () => {
  selectedCitation.value = latestAnswer.value?.citations[0] ?? null
  void scrollChatToBottom()
})

watch(
  () => [history.value.length, latestEntry.value?.answer?.created_at, errorMessage.value],
  () => {
    void scrollChatToBottom()
  },
  { flush: 'post' },
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
  selectedCitation.value = null

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

    selectedCitation.value = answer.citations[0] ?? null
    if (selectedCitation.value) {
      emit('selectCitation', selectedCitation.value)
    }

    if (createdSession || !props.sessionTitle || props.sessionTitle === 'New chat') {
      emit('sessionTitleSuggested', answer.session_id, titleFromQuestion(trimmedQuestion))
    }

    question.value = ''
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

function selectCitation(citation: ExcelCitation): void {
  selectedCitation.value = citation
  emit('selectCitation', citation)
}

function selectCitationById(citationId: string): void {
  const citation = latestAnswer.value?.citations.find((item) => item.citation_id === citationId)
  if (citation) {
    selectCitation(citation)
  }
}

function entryTimings(entry: ChatHistoryEntry): { stage: string; duration_seconds: number }[] {
  return entry.answer?.timings ?? []
}

function titleFromQuestion(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  return normalized.length > 56 ? `${normalized.slice(0, 53)}...` : normalized
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    route_model: 'Document selection',
    attach_documents: 'Attach documents',
    route_total: 'Selection total',
    load_rows: 'Load rows',
    answer_model: 'Model answer',
    verify_citations: 'Verify citations',
    answer_total: 'Answer total',
    chat_total: 'Full chain',
  }
  return labels[stage] ?? stage.replace(/_/g, ' ')
}

function formatSeconds(value: number): string {
  if (!Number.isFinite(value)) {
    return '-'
  }
  return `${value.toFixed(value < 10 ? 2 : 1)}s`
}

function timingValue(
  timings: { stage: string; duration_seconds: number }[],
  stage: string,
): number {
  return timings.find((timing) => timing.stage === stage)?.duration_seconds ?? 0
}
</script>

<template>
  <section class="chat-panel">
    <div class="chat-panel-head">
      <div>
        <p class="eyebrow">Chat</p>
        <h3>{{ currentSessionLabel }}</h3>
      </div>
      <span class="doc-count">{{ latestAnswer?.selected_documents.length ?? 0 }} docs</span>
    </div>

    <section class="chain-timing-panel" :class="{ collapsed: !isTimingExpanded }" aria-live="polite">
      <div class="timing-summary">
        <div>
          <p class="eyebrow">Chain Timing</p>
          <strong>{{ latestTotalSeconds ? formatSeconds(latestTotalSeconds) : 'No run yet' }}</strong>
        </div>
        <button
          type="button"
          class="timing-toggle"
          :aria-expanded="isTimingExpanded"
          @click="isTimingExpanded = !isTimingExpanded"
        >
          {{ timingToggleLabel }}
        </button>
      </div>
      <div v-if="isTimingExpanded && latestTimings.length > 0" class="timing-strip compact">
        <div
          v-for="timing in latestTimings"
          :key="`latest-${timing.stage}`"
          class="timing-pill"
          :class="{ total: timing.stage.endsWith('_total') }"
        >
          <span>{{ stageLabel(timing.stage) }}</span>
          <strong>{{ formatSeconds(timing.duration_seconds) }}</strong>
        </div>
      </div>
      <p v-else-if="isTimingExpanded" class="timing-placeholder">
        Timing appears after the next route or answer call.
      </p>
    </section>

    <div ref="chatScrollRegion" class="chat-scroll-region">
      <div class="chat-history">
        <template v-if="history.length > 0">
          <template v-for="(entry, entryIndex) in history" :key="entry.id">
            <div class="message user-message">
              <p>{{ entry.question }}</p>
              <span>User</span>
            </div>

            <article
              v-if="entry.answer"
              class="message assistant-message"
            >
              <div class="assistant-title">
                <span>AI</span>
                <strong>ExcelAI</strong>
              </div>
              <p v-if="entry.answer.insufficient_evidence" class="warning-text">Insufficient evidence.</p>
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
                  @click="selectCitationById(citationId)"
                >
                  [{{ citationId }}]
                </button>
              </div>
              <p v-if="entry.answer.answer_blocks.length === 0" class="empty-copy">No answer blocks returned.</p>
              <div v-if="entry.answer.warnings.length > 0" class="warning-list">
                <p v-for="warning in entry.answer.warnings" :key="warning">{{ warning }}</p>
              </div>
              <div v-if="entryTimings(entry).length > 0" class="timing-strip">
                <div
                  v-for="timing in entryTimings(entry)"
                  :key="`${entry.answer.created_at}-${timing.stage}`"
                  class="timing-pill"
                  :class="{ total: timing.stage.endsWith('_total') }"
                >
                  <span>{{ stageLabel(timing.stage) }}</span>
                  <strong>{{ formatSeconds(timing.duration_seconds) }}</strong>
                </div>
              </div>
            </article>

            <article
              v-else-if="isAsking && entryIndex === history.length - 1"
              class="message assistant-message loading-message"
            >
              <div class="assistant-title">
                <span>AI</span>
                <strong>ExcelAI</strong>
              </div>
              <p>Waiting for model response.</p>
            </article>
          </template>
        </template>

        <div v-else class="message assistant-message quiet-message">
          <div class="assistant-title">
            <span>AI</span>
            <strong>ExcelAI</strong>
          </div>
          <p>No messages in this session.</p>
        </div>
      </div>

      <div v-if="selectedCitation" class="evidence-panels">
        <SourceTracePanel :citation="selectedCitation" />
      </div>

      <p v-if="errorMessage" class="error-note chat-error-note">{{ errorMessage }}</p>
    </div>

    <form class="chat-input-card" @submit.prevent="submitQuestion">
      <textarea
        v-model="question"
        rows="3"
        placeholder="Ask about your Excel data..."
        @keydown.meta.enter="submitQuestion"
        @keydown.ctrl.enter="submitQuestion"
      />
      <div class="chat-input-actions">
        <span>Backend-verified citations</span>
        <button type="submit" :disabled="isAsking">
          {{ isAsking ? 'Asking...' : 'Send' }}
        </button>
      </div>
    </form>
  </section>
</template>
