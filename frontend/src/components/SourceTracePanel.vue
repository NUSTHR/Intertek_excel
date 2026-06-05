<script setup lang="ts">
import type { ExcelCitation } from '../types/chat'

defineProps<{
  citation: ExcelCitation | null
}>()
</script>

<template>
  <section v-if="citation" class="source-trace-panel">
    <p class="eyebrow">Source Trace</p>
    <h3>{{ citation.citation_id }} · {{ citation.row_id }}</h3>
    <p>{{ citation.sheet_name }}</p>
    <p v-if="citation.quote" class="muted">{{ citation.quote }}</p>
    <div class="source-row-preview">
      <span v-for="(cell, index) in citation.row.slice(0, 6)" :key="`${citation.row_id}-${index}`">
        {{ cell || '-' }}
      </span>
    </div>
  </section>
</template>
