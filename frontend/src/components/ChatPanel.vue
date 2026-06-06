<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  askExcelQuestion,
} from '../api/chat-api'
import type { ChatAnswer, ExcelCitation } from '../types/chat'
import CitationPanel from './CitationPanel.vue'
import SourceTracePanel from './SourceTracePanel.vue'

interface ChatHistoryEntry {
  question: string
  answer: ChatAnswer | null
}

const props = defineProps<{
  routerProvider: string | null
  routerModel: string | null
  answerProvider: string | null
  answerModel: string | null
}>()

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  selectCitation: [citation: ExcelCitation]
}>()

const question = ref<string>('')
const sessionId = ref<string>('')
const history = ref<ChatHistoryEntry[]>([])
const selectedCitation = ref<ExcelCitation | null>(null)
const errorMessage = ref<string>('')
const isAsking = ref<boolean>(false)

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

async function submitQuestion(): Promise<void> {
  const trimmedQuestion = question.value.trim()
  if (!trimmedQuestion) {
    errorMessage.value = 'Enter a question first.'
    return
  }
  errorMessage.value = ''
  isAsking.value = true
  selectedCitation.value = null
  const entry: ChatHistoryEntry = {
    question: trimmedQuestion,
    answer: null,
  }
  history.value = [...history.value, entry]
  try {
    const answer = await askExcelQuestion(
      trimmedQuestion,
      sessionId.value || null,
      {
        routerProvider: props.routerProvider ?? '',
        routerModel: props.routerModel ?? '',
        answerProvider: props.answerProvider ?? '',
        answerModel: props.answerModel ?? '',
      },
    )
    entry.answer = answer
    history.value = [...history.value]
    sessionId.value = answer.session_id
    emit('answerReceived', answer)
    selectedCitation.value = answer.citations[0] ?? null
    if (selectedCitation.value) {
      emit('selectCitation', selectedCitation.value)
    }
    question.value = ''
  } catch (error: unknown) {
    history.value = history.value.filter((item) => item !== entry)
    errorMessage.value = error instanceof Error ? error.message : 'Unexpected error.'
  } finally {
    isAsking.value = false
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
    <div class="panel-heading">
      <div>
        <p class="eyebrow">ExcelAI</p>
        <h3>Data Chat</h3>
      </div>
      <span class="doc-count">{{ latestAnswer?.selected_documents.length ?? 0 }} docs</span>
    </div>

    <section class="chain-timing-panel" aria-live="polite">
      <div class="timing-summary">
        <p class="eyebrow">Chain Timing</p>
        <strong>{{ latestTotalSeconds ? formatSeconds(latestTotalSeconds) : 'No run yet' }}</strong>
      </div>
      <div v-if="latestTimings.length > 0" class="timing-strip compact">
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
      <p v-else class="timing-placeholder">Timing appears after the next route or answer call.</p>
    </section>

    <div class="chat-history">
      <template v-if="history.length > 0">
        <template v-for="(entry, entryIndex) in history" :key="`${entryIndex}-${entry.question}`">
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
            <div v-if="entryTimings(entry).length > 0" class="timing-strip">
              <div
                v-for="timing in entryTimings(entry)"
                :key="`${entry.question}-${timing.stage}`"
                class="timing-pill"
                :class="{ total: timing.stage.endsWith('_total') }"
              >
                <span>{{ stageLabel(timing.stage) }}</span>
                <strong>{{ formatSeconds(timing.duration_seconds) }}</strong>
              </div>
            </div>
          </article>
        </template>
      </template>

      <div v-else class="message assistant-message quiet-message">
        <div class="assistant-title">
          <span>AI</span>
          <strong>ExcelAI</strong>
        </div>
        <p>No answers yet.</p>
      </div>
    </div>

    <div v-if="latestAnswer?.citations.length || selectedCitation" class="evidence-panels">
      <CitationPanel :citations="latestAnswer?.citations ?? []" @select-citation="selectCitation" />
      <SourceTracePanel :citation="selectedCitation" />
    </div>

    <p v-if="errorMessage" class="error-note">{{ errorMessage }}</p>

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
