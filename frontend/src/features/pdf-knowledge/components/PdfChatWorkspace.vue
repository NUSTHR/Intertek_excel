<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { renderMarkdown } from '../../../utils/markdown'
import type { PdfBreadcrumbItem, PdfChatMessage } from '../types'

const props = defineProps<{
  breadcrumbs: PdfBreadcrumbItem[]
  contextLabel: string
  messages: PdfChatMessage[]
  isAnswering: boolean
  enableDeepThinking: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  clearChat: []
  sendQuestion: [question: string]
  toggleDeepThinking: []
}>()

const draftQuestion = ref('')
const chatHistory = ref<HTMLElement | null>(null)
const canSend = computed(() => draftQuestion.value.trim().length > 0 && !props.isAnswering)
const visibleBreadcrumbs = computed<PdfBreadcrumbItem[]>(() => {
  const items = props.breadcrumbs.filter((item) => item.id !== 'knowledge-base')
  return items.length
    ? items
    : [{ id: 'current-context', label: props.contextLabel, active: true }]
})
const contextPathTitle = computed(() => (
  visibleBreadcrumbs.value.map((item) => item.label).join(' / ')
))
const contextPathLabel = computed(() => contextPathTitle.value)

watch(
  () => [props.messages.length, props.isAnswering],
  () => {
    void nextTick(() => {
      chatHistory.value?.scrollTo({
        top: chatHistory.value.scrollHeight,
        behavior: 'smooth',
      })
    })
  },
)

function submitQuestion(): void {
  const question = draftQuestion.value.trim()
  if (!question || props.isAnswering) {
    return
  }
  emit('sendQuestion', question)
  draftQuestion.value = ''
}

function onTextareaKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }
  event.preventDefault()
  submitQuestion()
}

</script>

<template>
  <main class="pdfkb-chat-workspace">
    <header class="pdfkb-chat-topbar">
      <div class="pdfkb-breadcrumb-context">
        <AppIcon name="account_tree" />
        <nav aria-label="PDF context">
          <span
            class="pdfkb-breadcrumb-item active"
            :title="contextPathTitle"
          >
            {{ contextPathLabel }}
          </span>
        </nav>
      </div>

      <div class="pdfkb-chat-topbar-actions">
        <button type="button" aria-label="Clear chat" @click="emit('clearChat')">
          <AppIcon name="close" />
        </button>
      </div>
    </header>

    <section ref="chatHistory" class="pdfkb-chat-history" aria-label="Chat history">
      <article v-if="messages.length === 0" class="pdfkb-chat-empty">
        <strong>Ask a question about indexed PDFs</strong>
        <span>{{ contextLabel }}</span>
      </article>

      <template v-for="message in messages" :key="message.id">
        <article
          v-if="message.role === 'user'"
          class="pdfkb-message-row user"
        >
          <div class="pdfkb-user-bubble">
            <p>{{ message.content }}</p>
          </div>
        </article>

        <article v-else class="pdfkb-message-row assistant" :class="{ error: message.error }">
          <div class="pdfkb-assistant-heading">
            <span class="pdfkb-assistant-avatar">
              <AppIcon name="auto_awesome" />
            </span>
            <span>AI Assistant</span>
          </div>

          <div class="pdfkb-assistant-bubble">
            <details
              v-if="message.reasoning"
              class="pdfkb-thinking-details"
            >
              <summary>
                <AppIcon name="psychology" />
                <span>Model reasoning</span>
              </summary>
              <div
                class="markdown-body pdfkb-thinking-markdown"
                v-html="renderMarkdown(message.reasoning)"
              ></div>
            </details>
            <div
              class="markdown-body pdfkb-answer-markdown"
              v-html="renderMarkdown(message.content)"
            ></div>
            <ul v-if="message.bullets?.length">
              <li v-for="bullet in message.bullets" :key="bullet.title">
                <strong>{{ bullet.title }}</strong>
                {{ bullet.text }}
              </li>
            </ul>
            <blockquote v-if="message.quote">{{ message.quote }}</blockquote>
            <p v-if="message.closing" class="pdfkb-muted-paragraph">
              {{ message.closing }}
            </p>
            <div v-if="message.citationIds?.length" class="pdfkb-message-citations">
              <span v-for="citationId in message.citationIds" :key="citationId">
                {{ citationId }}
              </span>
            </div>
            <p v-if="message.insufficientEvidence" class="pdfkb-muted-paragraph">
              The available PDF evidence may be insufficient for a complete answer.
            </p>
          </div>
        </article>
      </template>

      <article v-if="isAnswering" class="pdfkb-message-row assistant muted">
        <div class="pdfkb-typing-bubble" aria-label="AI is typing">
          <span></span>
          <span></span>
          <span></span>
        </div>
      </article>
    </section>

    <form class="pdfkb-input-area" aria-label="Ask a question" @submit.prevent="submitQuestion">
      <p v-if="errorMessage" class="pdfkb-chat-error">{{ errorMessage }}</p>
      <div class="pdfkb-input-shell">
        <textarea
          v-model="draftQuestion"
          rows="2"
          placeholder="Ask a question about indexed PDFs..."
          :disabled="isAnswering"
          @keydown="onTextareaKeydown"
        ></textarea>
        <div class="pdfkb-input-toolbar">
          <div class="pdfkb-chat-tools">
            <button
              type="button"
              class="pdfkb-thinking-toggle"
              :class="{ active: enableDeepThinking }"
              :aria-pressed="enableDeepThinking"
              :disabled="isAnswering"
              :title="enableDeepThinking ? 'Deep thinking on' : 'Deep thinking off'"
              :aria-label="enableDeepThinking ? 'Disable deep thinking' : 'Enable deep thinking'"
              @click="emit('toggleDeepThinking')"
            >
              <AppIcon name="psychology" />
              <span>Deep Think</span>
            </button>
            <span class="pdfkb-input-scope">{{ contextLabel }}</span>
          </div>
          <button
            type="submit"
            class="pdfkb-send-button"
            aria-label="Send message"
            :disabled="!canSend"
          >
            <AppIcon name="arrow_upward" />
          </button>
        </div>
      </div>
    </form>
  </main>
</template>
