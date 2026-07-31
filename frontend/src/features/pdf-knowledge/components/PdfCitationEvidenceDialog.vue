<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfCitationEvidenceDialogState } from '../types'

const props = defineProps<{
  dialog: PdfCitationEvidenceDialogState
}>()

const emit = defineEmits<{
  close: []
  retry: []
}>()

const closeButton = ref<HTMLButtonElement | null>(null)

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleDocumentKeydown)
  void nextTick(() => closeButton.value?.focus())
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <section
    class="dialog-backdrop pdfkb-evidence-dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="pdf-citation-evidence-title"
    @click.self="emit('close')"
  >
    <div class="app-dialog pdfkb-evidence-dialog">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">Indexed PDF Evidence</p>
          <h3 id="pdf-citation-evidence-title">
            Citation {{ dialog.citation.citationId }}
          </h3>
        </div>
        <button
          ref="closeButton"
          type="button"
          class="dialog-icon-button"
          aria-label="Close indexed evidence"
          @click="emit('close')"
        >
          <AppIcon name="close" />
        </button>
      </div>

      <div class="pdfkb-evidence-dialog-source">
        <strong>
          <AppIcon name="description" />
          {{ dialog.citation.fileName }}
        </strong>
        <span>{{ dialog.citation.location }}</span>
      </div>

      <div
        v-if="dialog.status === 'loading'"
        class="pdfkb-evidence-dialog-state"
        role="status"
      >
        <AppIcon name="hourglass_empty" />
        <strong>Loading indexed evidence…</strong>
        <span>The exact cited PDF chunk is being retrieved.</span>
      </div>

      <div
        v-else-if="dialog.status === 'failed'"
        class="pdfkb-evidence-dialog-state error"
        role="alert"
      >
        <AppIcon name="error_outline" />
        <strong>Indexed evidence is unavailable</strong>
        <span>{{ dialog.errorMessage }}</span>
        <button type="button" class="dialog-secondary" @click="emit('retry')">
          Retry
        </button>
      </div>

      <div
        v-else-if="dialog.evidence"
        class="pdfkb-evidence-dialog-content custom-scrollbar"
      >
        <p>{{ dialog.evidence.text }}</p>
      </div>
    </div>
  </section>
</template>
