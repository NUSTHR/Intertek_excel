<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfBreadcrumbItem, PdfChatMessage } from '../types'

const props = defineProps<{
  breadcrumbs: PdfBreadcrumbItem[]
  messages: PdfChatMessage[]
  isAnswering: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  clearChat: []
  sendQuestion: [question: string]
}>()

const draftQuestion = ref('')
const chatHistory = ref<HTMLElement | null>(null)
const canSend = computed(() => draftQuestion.value.trim().length > 0 && !props.isAnswering)

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

function messageParagraphs(message: PdfChatMessage): string[] {
  return message.content
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
}
</script>

<template>
  <main class="pdfkb-chat-workspace">
    <header class="pdfkb-chat-topbar">
      <div class="pdfkb-breadcrumb-context">
        <AppIcon name="grid_view" />
        <span>Context:</span>
        <nav aria-label="PDF context">
          <template v-for="(item, index) in breadcrumbs" :key="item.id">
            <AppIcon v-if="index > 0" name="chevron_right" class="pdfkb-breadcrumb-chevron" />
            <span
              class="pdfkb-breadcrumb-item"
              :class="{ active: item.active }"
            >
              <AppIcon v-if="item.icon" :name="item.icon" />
              {{ item.label }}
            </span>
          </template>
        </nav>
      </div>

      <div class="pdfkb-chat-topbar-actions">
        <button type="button" aria-label="Export chat unavailable" disabled>
          <AppIcon name="download" />
        </button>
        <button type="button" aria-label="Clear chat" @click="emit('clearChat')">
          <AppIcon name="close" />
        </button>
      </div>
    </header>

    <section ref="chatHistory" class="pdfkb-chat-history" aria-label="Chat history">
      <div class="pdfkb-time-marker">PDF Knowledge Chat</div>

      <article v-if="messages.length === 0" class="pdfkb-chat-empty">
        <AppIcon name="auto_awesome" />
        <strong>Ask a question about indexed PDFs</strong>
        <span>Answers will use retrieved PDF chunks and show source citations.</span>
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
            <p
              v-for="(paragraph, index) in messageParagraphs(message)"
              :key="`${message.id}-${index}`"
            >
              {{ paragraph }}
            </p>
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

          <div class="pdfkb-inline-actions">
            <button type="button" disabled>
              <AppIcon name="content_copy" />
              <span>Copy</span>
            </button>
            <button type="button" disabled>
              <AppIcon name="check" />
              <span>Helpful</span>
            </button>
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
          <div class="pdfkb-input-tools">
            <button type="button" aria-label="Attach file unavailable" disabled>
              <AppIcon name="attach_file" />
            </button>
            <button type="button" aria-label="Voice input unavailable" disabled>
              <AppIcon name="psychology" />
            </button>
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
      <p>AI can make mistakes. Verify critical information.</p>
    </form>
  </main>
</template>
