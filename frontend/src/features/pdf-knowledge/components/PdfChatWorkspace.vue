<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { renderMarkdown } from '../../../utils/markdown'
import type {
  PdfBreadcrumbItem,
  PdfChatSourceDocument,
  PdfChatTurnView,
} from '../types'
import PdfChatDataSources from './PdfChatDataSources.vue'

const props = defineProps<{
  breadcrumbs: PdfBreadcrumbItem[]
  activeSessionId: string
  contextLabel: string
  turns: PdfChatTurnView[]
  sourceDocuments: PdfChatSourceDocument[]
  activeCitationKey: string
  isAnswering: boolean
  isSessionLoading: boolean
  enableDeepThinking: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  clearChat: []
  selectCitation: [turnId: string, citationId: string]
  selectSourceDocument: [document: PdfChatSourceDocument]
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
const markdownCache = new Map<string, string>()
const markdownCacheLimit = 256

watch(
  () => [
    props.activeSessionId,
    props.turns.length,
    props.turns.at(-1)?.status,
    props.isAnswering,
  ],
  (current, previous) => {
    const switchedSession = current[0] !== previous?.[0]
    void nextTick(() => {
      chatHistory.value?.scrollTo({
        top: chatHistory.value.scrollHeight,
        behavior: switchedSession ? 'auto' : 'smooth',
      })
    })
  },
)

function renderMarkdownCached(source: string): string {
  const cached = markdownCache.get(source)
  if (cached !== undefined) {
    markdownCache.delete(source)
    markdownCache.set(source, cached)
    return cached
  }
  const rendered = renderMarkdown(source)
  markdownCache.set(source, rendered)
  if (markdownCache.size > markdownCacheLimit) {
    const oldestKey = markdownCache.keys().next().value
    if (oldestKey !== undefined) {
      markdownCache.delete(oldestKey)
    }
  }
  return rendered
}

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
      <p
        v-if="isSessionLoading"
        class="pdfkb-chat-session-loading"
        role="status"
        aria-live="polite"
      >
        Loading chat history...
      </p>
      <PdfChatDataSources
        :documents="sourceDocuments"
        @select-document="emit('selectSourceDocument', $event)"
      />

      <article v-if="turns.length === 0" class="pdfkb-chat-empty">
        <strong>Ask a question about indexed PDFs</strong>
        <span>{{ contextLabel }}</span>
      </article>

      <template v-for="turn in turns" :key="turn.turnId">
        <article class="pdfkb-message-row user">
          <div class="pdfkb-user-bubble">
            <p>{{ turn.question }}</p>
          </div>
        </article>

        <article
          v-if="turn.status === 'complete' && turn.answer"
          class="pdfkb-message-row assistant"
        >
          <div class="pdfkb-assistant-heading">
            <span class="pdfkb-assistant-avatar">
              <AppIcon name="auto_awesome" />
            </span>
            <span>AI Assistant</span>
          </div>

          <div class="pdfkb-assistant-bubble">
            <p v-if="turn.answer.insufficientEvidence" class="pdfkb-muted-paragraph">
              {{
                /[\u3400-\u9fff]/.test(turn.question)
                  ? '当前所选 PDF 范围内的证据可能不足以形成完整回答。'
                  : 'The selected PDF scope may not contain enough evidence for a complete answer.'
              }}
            </p>
            <section
              v-for="block in turn.answer.blocks"
              :key="block.id"
              class="pdfkb-answer-block"
            >
              <details
                v-if="block.reasoning"
                class="pdfkb-thinking-details"
              >
                <summary>
                  <AppIcon name="psychology" />
                  <span>Model reasoning</span>
                </summary>
                <div
                  class="markdown-body pdfkb-thinking-markdown"
                  v-html="renderMarkdownCached(block.reasoning)"
                ></div>
              </details>
              <div
                class="markdown-body pdfkb-answer-markdown"
                v-html="renderMarkdownCached(block.text)"
              ></div>
              <div
                v-if="block.citations.length || block.unresolvedCitationIds.length"
                class="pdfkb-message-citations"
              >
                <button
                  v-for="citation in block.citations"
                  :key="citation.key"
                  type="button"
                  :class="{ active: activeCitationKey === citation.key }"
                  :aria-label="`Open PDF citation ${citation.citationId}`"
                  :aria-pressed="activeCitationKey === citation.key"
                  @click="emit('selectCitation', turn.turnId, citation.citationId)"
                >
                  {{ citation.citationId }}
                </button>
                <button
                  v-for="citationId in block.unresolvedCitationIds"
                  :key="`${block.id}:unresolved:${citationId}`"
                  type="button"
                  disabled
                  :aria-label="`Unavailable PDF citation ${citationId}`"
                >
                  {{ citationId }}
                </button>
              </div>
            </section>
            <div v-if="turn.answer.blocks.length === 0" class="pdfkb-muted-paragraph">
              No answer text was generated.
            </div>
            <div v-if="turn.answer.warnings.length" class="pdfkb-answer-warnings">
              <p v-for="warning in turn.answer.warnings" :key="warning">{{ warning }}</p>
            </div>
          </div>
        </article>

        <article
          v-else-if="turn.status === 'failed'"
          class="pdfkb-message-row assistant error"
        >
          <div class="pdfkb-assistant-heading">
            <span class="pdfkb-assistant-avatar">
              <AppIcon name="error" />
            </span>
            <span>AI Assistant</span>
          </div>
          <div class="pdfkb-assistant-bubble">
            <p>{{ turn.errorMessage }}</p>
          </div>
        </article>
      </template>

      <article
        v-if="isAnswering"
        class="pdfkb-message-row assistant pdfkb-thinking-message"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <div class="pdfkb-assistant-heading pdfkb-thinking-title">
          <span class="pdfkb-assistant-avatar">
            <AppIcon name="auto_awesome" />
          </span>
          <span>Thinking...</span>
        </div>
        <div class="pdfkb-thinking-bubble">
          <div class="pdfkb-thinking-bars" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="pdfkb-thinking-copy">
            <strong>{{ enableDeepThinking ? 'Deep reasoning' : 'Tracing evidence' }}</strong>
            <span>
              {{
                enableDeepThinking
                  ? 'Comparing PDF evidence. Verifying citations. Composing.'
                  : 'Checking PDF evidence. Verifying citations. Composing.'
              }}
            </span>
          </div>
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
