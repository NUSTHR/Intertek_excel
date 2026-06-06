<script setup lang="ts">
import type { ExcelCitation } from '../types/chat'

defineProps<{
  citations: ExcelCitation[]
}>()

const emit = defineEmits<{
  selectCitation: [citation: ExcelCitation]
}>()
</script>

<template>
  <section v-if="citations.length > 0" class="citation-panel">
    <div class="panel-heading">
      <h3>Citations</h3>
      <span>{{ citations.length }}</span>
    </div>
    <button
      v-for="citation in citations"
      :key="`${citation.version_id}-${citation.sheet_id}-${citation.row_id}`"
      type="button"
      class="citation-row"
      @click="emit('selectCitation', citation)"
    >
      <strong>{{ citation.citation_id }}</strong>
      <span>{{ citation.sheet_name }}</span>
    </button>
  </section>
</template>
