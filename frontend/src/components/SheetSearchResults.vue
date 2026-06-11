<script setup lang="ts">
import { computed } from 'vue'

import type { SheetSearchMatch } from '../types/excel-assets'
import AppIcon from './AppIcon.vue'

const props = withDefaults(
  defineProps<{
    summary: string
    matches: SheetSearchMatch[]
    totalMatches: number
    activeRowId: string
    hasError: boolean
    disabled: boolean
    variant?: 'default' | 'file-preview'
  }>(),
  {
    variant: 'default',
  },
)

const emit = defineEmits<{
  select: [match: SheetSearchMatch]
}>()

const displayedMatches = computed(() => props.matches)

const variantClass = computed(() => (
  `sheet-search-results--${props.variant}`
))

const overflowLabel = computed(() => {
  if (props.totalMatches <= displayedMatches.value.length) {
    return ''
  }
  return `Showing ${displayedMatches.value.length} of ${props.totalMatches}`
})

function previewText(match: SheetSearchMatch): string {
  return match.row.slice(1, 4).filter(Boolean).join(' / ') || '-'
}

function resultLabel(match: SheetSearchMatch): string {
  return `${match.sheet.sheet_name} · ${match.mapping.row_id}`
}
</script>

<template>
  <section
    class="sheet-search-results"
    :class="[{ error: hasError }, variantClass]"
    aria-live="polite"
  >
    <div class="sheet-search-summary">
      <AppIcon :name="hasError ? 'close' : 'search'" />
      <strong>{{ summary }}</strong>
    </div>
    <div v-if="displayedMatches.length > 0" class="sheet-search-result-list">
      <button
        v-for="match in displayedMatches"
        :key="`${match.mapping.sheet_id}:${match.mapping.row_id}`"
        type="button"
        :class="{ active: activeRowId === match.mapping.row_id }"
        :disabled="disabled"
        @click="emit('select', match)"
      >
        <span>{{ resultLabel(match) }}</span>
        <strong>{{ previewText(match) }}</strong>
      </button>
      <span v-if="overflowLabel" class="sheet-search-more">
        {{ overflowLabel }}
      </span>
    </div>
  </section>
</template>
