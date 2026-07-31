<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfChatSourceDocument } from '../types'

const props = defineProps<{
  documents: PdfChatSourceDocument[]
}>()

const emit = defineEmits<{
  selectDocument: [document: PdfChatSourceDocument]
}>()

const activeIndex = ref(0)
const normalizedIndex = computed(() => {
  if (props.documents.length === 0) {
    return 0
  }
  return Math.min(activeIndex.value, props.documents.length - 1)
})
const activeDocument = computed(() => props.documents[normalizedIndex.value])
const countLabel = computed(() => {
  const count = props.documents.length
  return `${count} Document${count === 1 ? '' : 's'}`
})
const positionLabel = computed(() => {
  if (props.documents.length === 0) {
    return ''
  }
  return `${normalizedIndex.value + 1} / ${props.documents.length}`
})

watch(
  () => props.documents.map((document) => document.key).join('|'),
  () => {
    activeIndex.value = 0
  },
)

function step(direction: -1 | 1): void {
  const count = props.documents.length
  if (count <= 1) {
    return
  }
  activeIndex.value = (normalizedIndex.value + direction + count) % count
}
</script>

<template>
  <section class="chat-data-sources-card" aria-label="Data sources for current PDF turn">
    <div class="chat-data-sources-head">
      <div>
        <span>Data Sources</span>
        <strong>{{ countLabel }}</strong>
      </div>
    </div>
    <div class="chat-data-source-list">
      <div
        v-if="activeDocument"
        :key="activeDocument.key"
        class="chat-data-source-row"
      >
        <button
          type="button"
          class="pdfkb-source-document-main"
          @click="emit('selectDocument', activeDocument)"
        >
          <span class="chat-source-file-icon">
            <AppIcon name="description" />
          </span>
          <span class="chat-source-copy">
            <strong :title="activeDocument.title">{{ activeDocument.title }}</strong>
            <span>Active Source</span>
          </span>
          <span class="chat-source-status" aria-hidden="true">
            <span></span>
          </span>
        </button>
        <span class="chat-source-pager">
          <small v-if="positionLabel">{{ positionLabel }}</small>
          <button
            type="button"
            aria-label="Previous PDF data source"
            :disabled="documents.length <= 1"
            @click="step(-1)"
          >
            <AppIcon name="keyboard_arrow_up" />
          </button>
          <button
            type="button"
            aria-label="Next PDF data source"
            :disabled="documents.length <= 1"
            @click="step(1)"
          >
            <AppIcon name="keyboard_arrow_down" />
          </button>
        </span>
      </div>
      <div v-else class="chat-data-source-empty">
        <span class="chat-source-file-icon muted">
          <AppIcon name="description" />
        </span>
        <span class="chat-source-copy">
          <strong>No active source</strong>
          <span>Ask about a PDF document</span>
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
</template>
