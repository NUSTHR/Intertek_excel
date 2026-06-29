<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { PdfCitation } from '../types'

defineProps<{
  citations: PdfCitation[]
  collapsed: boolean
}>()

const emit = defineEmits<{
  toggleCollapsed: []
}>()

function iconForCitation(citation: PdfCitation): string {
  return citation.fileKind === 'table' ? 'table_chart' : 'description'
}
</script>

<template>
  <aside class="pdfkb-citations" :class="{ collapsed }" aria-label="Source citations">
    <button
      type="button"
      class="pdfkb-citation-collapse"
      :aria-label="collapsed ? 'Expand source citations' : 'Collapse source citations'"
      @click="emit('toggleCollapsed')"
    >
      <AppIcon :name="collapsed ? 'chevron_left' : 'chevron_right'" />
    </button>

    <template v-if="!collapsed">
      <header class="pdfkb-citation-header">
        <div>
          <AppIcon name="schema" />
          <h2>Source Citations</h2>
        </div>
        <span class="pdfkb-match-count">
          <strong>{{ citations.length }}</strong>
          <span>Matches</span>
        </span>
      </header>

      <div v-if="citations.length === 0" class="pdfkb-citation-empty">
        <AppIcon name="schema" />
        <strong>No sources yet</strong>
        <span>Ask a PDF question to see retrieved citations.</span>
      </div>

      <div v-else class="pdfkb-citation-list">
        <article
          v-for="citation in citations"
          :key="citation.id"
          class="pdfkb-citation-card"
          :class="citation.tone"
        >
          <div class="pdfkb-citation-accent" aria-hidden="true"></div>
          <div class="pdfkb-citation-card-head">
            <div>
              <span class="pdfkb-citation-source">
                <AppIcon v-if="citation.tone === 'crossReference'" name="attach_file" />
                {{ citation.sourceLabel }}
              </span>
              <strong>
                <AppIcon :name="iconForCitation(citation)" />
                {{ citation.fileName }}
              </strong>
            </div>
            <span class="pdfkb-citation-match">{{ citation.matchLabel }}</span>
          </div>

          <p class="pdfkb-citation-excerpt">{{ citation.excerpt }}</p>

          <div class="pdfkb-citation-location">
            <span>
              <AppIcon :name="citation.fileKind === 'table' ? 'table_rows' : 'push_pin'" />
              {{ citation.location }}
            </span>
            <AppIcon name="fullscreen" />
          </div>
        </article>
      </div>
    </template>
  </aside>
</template>
