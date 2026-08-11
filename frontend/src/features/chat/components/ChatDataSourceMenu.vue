<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { useOutsideClose } from '../../../shared/file-workspace/composables/use-outside-close'
import type { SelectedDocument } from '../../../types/chat'

const props = defineProps<{
  documents: SelectedDocument[]
  documentTitles: Record<string, string>
}>()

const emit = defineEmits<{
  select: [document: SelectedDocument]
}>()

const containerRef = ref<HTMLElement | null>(null)
const isOpen = ref(false)

useOutsideClose({
  isOpen: computed(() => isOpen.value),
  containerRef,
  onClose: () => {
    isOpen.value = false
  },
})

function selectDocument(document: SelectedDocument): void {
  isOpen.value = false
  emit('select', document)
}

function documentTitle(document: SelectedDocument): string {
  return props.documentTitles[document.file_id] ?? 'Referenced workbook'
}

function documentKey(document: SelectedDocument): string {
  return `${document.file_id}:${document.version_id}`
}
</script>

<template>
  <span ref="containerRef" class="chat-source-menu-control">
    <button
      type="button"
      class="chat-source-menu"
      aria-label="Data source options"
      :aria-expanded="isOpen"
      aria-haspopup="menu"
      @click="isOpen = !isOpen"
    >
      <AppIcon name="more_vert" />
    </button>

    <span v-if="isOpen" class="chat-source-options-popover" role="menu">
      <span v-if="documents.length === 0" class="chat-source-options-empty" role="status">
        Sources are selected automatically when you ask a question.
      </span>
      <template v-else>
        <button
          v-for="document in documents"
          :key="documentKey(document)"
          type="button"
          role="menuitem"
          @click="selectDocument(document)"
        >
          <AppIcon name="description" />
          <span>
            <strong>{{ documentTitle(document) }}</strong>
            <small>{{ document.reason || 'Answer source' }}</small>
          </span>
        </button>
      </template>
    </span>
  </span>
</template>
