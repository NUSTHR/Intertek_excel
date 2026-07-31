<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfCitation } from '../types'
import { pdfCitationCountLabel } from '../utils/pdf-citation-presentation'

const props = defineProps<{
  citations: PdfCitation[]
  collapsed: boolean
  activeCitationKey: string
  focusRequestId: number
}>()

const emit = defineEmits<{
  openCitation: [citation: PdfCitation]
  toggleCollapsed: []
}>()

const citationList = ref<HTMLElement | null>(null)
const citationCountLabel = computed(() => pdfCitationCountLabel(props.citations.length))

function iconForCitation(citation: PdfCitation): string {
  return citation.fileKind === 'table' ? 'table_chart' : 'description'
}

function openCitation(citation: PdfCitation): void {
  emit('openCitation', citation)
}

function handleCitationKeydown(event: KeyboardEvent, citation: PdfCitation): void {
  if (event.key !== 'Enter' && event.key !== ' ') {
    return
  }
  event.preventDefault()
  openCitation(citation)
}

watch(
  () => [
    props.activeCitationKey,
    props.collapsed,
    props.focusRequestId,
  ] as const,
  ([activeCitationKey, collapsed, focusRequestId], previousState) => {
    if (!activeCitationKey || collapsed) {
      return
    }
    void nextTick(() => {
      const card = Array.from(
        citationList.value?.querySelectorAll<HTMLElement>('[data-citation-key]') ?? [],
      ).find((candidate) => candidate.dataset.citationKey === activeCitationKey)
      card?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      if (focusRequestId !== previousState?.[2]) {
        card?.focus({ preventScroll: true })
      }
    })
  },
)
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
          <span>{{ citationCountLabel }}</span>
        </span>
      </header>

      <div v-if="citations.length === 0" class="pdfkb-citation-empty">
        <AppIcon name="schema" />
        <strong>No sources yet</strong>
        <span>Ask a PDF question to see source citations.</span>
      </div>

      <div v-else ref="citationList" class="pdfkb-citation-list">
        <article
          v-for="citation in citations"
          :key="citation.key"
          class="pdfkb-citation-card"
          :class="[
            citation.visualTone,
            { active: activeCitationKey === citation.key },
          ]"
          :data-citation-key="citation.key"
          role="button"
          tabindex="0"
          :aria-label="`View full indexed evidence for citation ${citation.citationId}`"
          :aria-pressed="activeCitationKey === citation.key"
          @click="openCitation(citation)"
          @keydown="handleCitationKeydown($event, citation)"
        >
          <div class="pdfkb-citation-accent" aria-hidden="true"></div>
          <div class="pdfkb-citation-card-head">
            <div>
              <span class="pdfkb-citation-source">
                <AppIcon
                  v-if="citation.visualTone === 'crossReference'"
                  name="attach_file"
                />
                {{ citation.sourceLabel }}
              </span>
              <strong>
                <AppIcon :name="iconForCitation(citation)" />
                {{ citation.fileName }}
              </strong>
            </div>
            <span v-if="citation.matchLabel" class="pdfkb-citation-match">
              {{ citation.matchLabel }}
            </span>
          </div>

          <p class="pdfkb-citation-excerpt">{{ citation.excerpt }}</p>

          <div class="pdfkb-citation-location">
            <span :title="citation.location">
              <AppIcon :name="citation.fileKind === 'table' ? 'table_rows' : 'push_pin'" />
              {{ citation.location }}
            </span>
            <AppIcon
              name="fullscreen"
              aria-hidden="true"
              title="Open indexed evidence"
            />
          </div>
        </article>
      </div>
    </template>
  </aside>
</template>
