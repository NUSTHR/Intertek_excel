<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  answerRoutedExcelQuestion,
  createChatSession,
  routeExcelQuestion,
} from '../api/chat-api'
import type { ChatAnswer, ChatRouteResult, ExcelCitation } from '../types/chat'
import CitationPanel from './CitationPanel.vue'
import SourceTracePanel from './SourceTracePanel.vue'

interface ChatHistoryEntry {
  question: string
  route: ChatRouteResult | null
  answer: ChatAnswer | null
}

const props = defineProps<{
  routerModel: string | null
  answerModel: string | null
}>()

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  routeReceived: [route: ChatRouteResult]
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
    route: null,
    answer: null,
  }
  history.value = [...history.value, entry]
  try {
    if (!sessionId.value) {
      sessionId.value = (await createChatSession()).session_id
    }
    const route = await routeExcelQuestion(trimmedQuestion, sessionId.value, props.routerModel)
    sessionId.value = route.session_id
    entry.route = route
    history.value = [...history.value]
    emit('routeReceived', route)
    const answer = await answerRoutedExcelQuestion(
      trimmedQuestion,
      sessionId.value,
      props.answerModel,
      route.selected_documents.map((document) => document.version_id),
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
</script>

<template>
  <section class="chat-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">ExcelAI</p>
        <h3>Data Chat</h3>
      </div>
      <span class="doc-count">{{ latestAnswer?.selected_documents.length ?? latestEntry?.route?.selected_documents.length ?? 0 }} docs</span>
    </div>

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
        <p>No answers yet.</p>
      </div>
    </div>

    <CitationPanel :citations="latestAnswer?.citations ?? []" @select-citation="selectCitation" />
    <SourceTracePanel :citation="selectedCitation" />

    <p v-if="errorMessage" class="error-note">{{ errorMessage }}</p>

    <div class="chat-input-card">
      <textarea
        v-model="question"
        rows="3"
        placeholder="Ask about your Excel data..."
        @keydown.meta.enter="submitQuestion"
        @keydown.ctrl.enter="submitQuestion"
      />
      <div class="chat-input-actions">
        <span>Backend-verified citations</span>
        <button type="button" :disabled="isAsking" @click="submitQuestion">
          {{ isAsking ? 'Asking...' : 'Send' }}
        </button>
      </div>
    </div>
  </section>
</template>
