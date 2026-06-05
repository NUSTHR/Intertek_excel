<script setup lang="ts">
import { ref } from 'vue'

import {
  answerRoutedExcelQuestion,
  createChatSession,
  routeExcelQuestion,
} from '../api/chat-api'
import type { ChatAnswer, ChatRouteResult, ExcelCitation } from '../types/chat'
import CitationPanel from './CitationPanel.vue'
import SourceTracePanel from './SourceTracePanel.vue'

const emit = defineEmits<{
  answerReceived: [answer: ChatAnswer]
  routeReceived: [route: ChatRouteResult]
  selectCitation: [citation: ExcelCitation]
}>()

const question = ref<string>('')
const sessionId = ref<string>('')
const lastQuestion = ref<string>('')
const answer = ref<ChatAnswer | null>(null)
const selectedCitation = ref<ExcelCitation | null>(null)
const errorMessage = ref<string>('')
const isAsking = ref<boolean>(false)

async function submitQuestion(): Promise<void> {
  const trimmedQuestion = question.value.trim()
  if (!trimmedQuestion) {
    errorMessage.value = 'Enter a question first.'
    return
  }
  errorMessage.value = ''
  isAsking.value = true
  lastQuestion.value = trimmedQuestion
  answer.value = null
  selectedCitation.value = null
  try {
    if (!sessionId.value) {
      sessionId.value = (await createChatSession()).session_id
    }
    const route = await routeExcelQuestion(trimmedQuestion, sessionId.value)
    sessionId.value = route.session_id
    emit('routeReceived', route)
    answer.value = await answerRoutedExcelQuestion(trimmedQuestion, sessionId.value)
    sessionId.value = answer.value.session_id
    emit('answerReceived', answer.value)
    selectedCitation.value = answer.value.citations[0] ?? null
    if (selectedCitation.value) {
      emit('selectCitation', selectedCitation.value)
    }
    question.value = ''
  } catch (error: unknown) {
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
  const citation = answer.value?.citations.find((item) => item.citation_id === citationId)
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
      <span class="doc-count">{{ answer?.selected_documents.length ?? 0 }} docs</span>
    </div>

    <div class="chat-history">
      <div v-if="lastQuestion" class="message user-message">
        <p>{{ lastQuestion }}</p>
        <span>User</span>
      </div>

      <article v-if="isAsking" class="message assistant-message loading-message">
        <div class="assistant-title">
          <span>AI</span>
          <strong>ExcelAI</strong>
        </div>
        <p>Waiting for model response.</p>
      </article>

      <article v-else-if="answer" class="message assistant-message">
        <div class="assistant-title">
          <span>AI</span>
          <strong>ExcelAI</strong>
        </div>
        <p v-if="answer.insufficient_evidence" class="warning-text">Insufficient evidence.</p>
        <div
          v-for="(block, blockIndex) in answer.answer_blocks"
          :key="`${answer.created_at}-${blockIndex}`"
          class="answer-block"
        >
          <p>{{ block.text }}</p>
          <button
            v-for="citationId in block.citation_ids"
            :key="`${blockIndex}-${citationId}`"
            type="button"
            class="citation-chip"
            @click="selectCitationById(citationId)"
          >
            [{{ citationId }}]
          </button>
        </div>
        <p v-if="answer.answer_blocks.length === 0" class="empty-copy">No answer blocks returned.</p>
        <div v-if="answer.warnings.length > 0" class="warning-list">
          <p v-for="warning in answer.warnings" :key="warning">{{ warning }}</p>
        </div>
      </article>

      <div v-else class="message assistant-message quiet-message">
        <div class="assistant-title">
          <span>AI</span>
          <strong>ExcelAI</strong>
        </div>
        <p>No answers yet.</p>
      </div>
    </div>

    <CitationPanel :citations="answer?.citations ?? []" @select-citation="selectCitation" />
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
