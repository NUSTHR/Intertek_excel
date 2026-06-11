<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import type {
  DocumentSummary,
  DocumentSummaryUpdate,
  SheetSummaryUpdate,
} from '../types/document-summary'
import AppIcon from './AppIcon.vue'

const props = defineProps<{
  summary: DocumentSummary | null
  isGenerating: boolean
  isSaving: boolean
  canGenerate: boolean
}>()

const emit = defineEmits<{
  generate: []
  save: [payload: DocumentSummaryUpdate, onSaved: (saved: boolean) => void]
}>()

const isEditing = ref(false)
const isAddingTag = ref(false)
const isSavePending = ref(false)
const draftDocumentTitle = ref('')
const draftSummaryText = ref('')
const draftBusinessDomain = ref('')
const draftKeyTopicsText = ref('')
const draftSuitableQuestionsText = ref('')
const draftUnsuitableQuestionsText = ref('')
const draftRoutingNotes = ref('')
const draftSheetSummaries = ref<SheetSummaryUpdate[]>([])
const newTagText = ref('')
const newTagInput = ref<HTMLInputElement | null>(null)

const primaryTags = computed(() => props.summary?.key_topics ?? [])

const isSavingSummary = computed(() => props.isSaving || isSavePending.value)

const summaryTitle = computed(() => {
  const value = props.summary?.document_title || props.summary?.business_domain || ''
  return truncateMiddle(value, 52)
})

const summaryText = computed(() => props.summary?.summary_text.trim() ?? '')

const routingTags = computed(() => {
  const summary = props.summary
  if (!summary) {
    return []
  }
  return uniqueStrings([
    ...summary.positive_routing_terms,
    ...summary.exact_identifiers,
    ...summary.negative_routing_terms,
  ]).filter((tag) => !summary.key_topics.some((topic) => isSameText(topic, tag)))
})

const questionBlocks = computed<Array<{
  key: string
  icon: string
  title: string
  items: string[]
}>>(() => {
  const summary = props.summary
  return [
    {
      key: 'suitable',
      icon: 'help',
      title: 'Good Questions',
      items: summary?.suitable_questions ?? [],
    },
    {
      key: 'unsuitable',
      icon: 'close',
      title: 'Out of Scope',
      items: summary?.unsuitable_questions ?? [],
    },
  ]
})

const sheetSummaries = computed(() => props.summary?.sheet_summaries ?? [])

const sheetCount = computed(() => sheetSummaries.value.length)

const generateLabel = computed(() => {
  if (props.isGenerating) {
    return 'Generating...'
  }
  return props.summary ? 'Regenerate' : 'Generate Summary'
})

watch(
  () => props.summary?.summary_id,
  () => {
    resetDraft()
    isEditing.value = false
    isAddingTag.value = false
    newTagText.value = ''
  },
)

watch(isEditing, (editing) => {
  if (editing) {
    resetDraft()
  }
})

function resetDraft(): void {
  const summary = props.summary
  if (!summary) {
    draftDocumentTitle.value = ''
    draftSummaryText.value = ''
    draftBusinessDomain.value = ''
    draftKeyTopicsText.value = ''
    draftSuitableQuestionsText.value = ''
    draftUnsuitableQuestionsText.value = ''
    draftRoutingNotes.value = ''
    draftSheetSummaries.value = []
    return
  }
  draftDocumentTitle.value = summary.document_title
  draftSummaryText.value = summary.summary_text
  draftBusinessDomain.value = summary.business_domain
  draftKeyTopicsText.value = summary.key_topics.join('\n')
  draftSuitableQuestionsText.value = summary.suitable_questions.join('\n')
  draftUnsuitableQuestionsText.value = summary.unsuitable_questions.join('\n')
  draftRoutingNotes.value = summary.routing_notes
  draftSheetSummaries.value = summary.sheet_summaries.map((sheet) => ({
    sheet_id: sheet.sheet_id,
    sheet_name: sheet.sheet_name,
    summary: sheet.summary,
    important_columns: [...sheet.important_columns],
    likely_question_types: [...sheet.likely_question_types],
    header_terms: [...sheet.header_terms],
    sampled_identifiers: [...sheet.sampled_identifiers],
  }))
}

function startEditing(): void {
  if (!props.summary) {
    return
  }
  isEditing.value = true
}

function cancelEditing(): void {
  resetDraft()
  isEditing.value = false
}

function saveDraft(): void {
  if (!props.summary) {
    return
  }
  requestSave(
    {
      document_title: draftDocumentTitle.value,
      summary_text: draftSummaryText.value,
      business_domain: draftBusinessDomain.value,
      key_topics: parseLines(draftKeyTopicsText.value),
      suitable_questions: parseLines(draftSuitableQuestionsText.value),
      unsuitable_questions: parseLines(draftUnsuitableQuestionsText.value),
      sheet_summaries: draftSheetSummaries.value.map((sheet) => ({
        sheet_id: sheet.sheet_id,
        sheet_name: sheet.sheet_name.trim(),
        summary: sheet.summary.trim(),
        important_columns: uniqueStrings(sheet.important_columns),
        likely_question_types: uniqueStrings(sheet.likely_question_types),
        header_terms: uniqueStrings(sheet.header_terms),
        sampled_identifiers: uniqueStrings(sheet.sampled_identifiers),
      })),
      routing_notes: draftRoutingNotes.value,
    },
    () => {
      isEditing.value = false
    },
  )
}

async function openTagInput(): Promise<void> {
  if (!props.summary) {
    return
  }
  isAddingTag.value = true
  await nextTick()
  newTagInput.value?.focus()
}

function cancelTagInput(): void {
  isAddingTag.value = false
  newTagText.value = ''
}

function addTag(): void {
  const tag = cleanTag(newTagText.value)
  const summary = props.summary
  if (!summary || !tag) {
    cancelTagInput()
    return
  }
  if (summary.key_topics.some((topic) => isSameText(topic, tag))) {
    cancelTagInput()
    return
  }
  requestSave({ key_topics: [...summary.key_topics, tag] }, cancelTagInput)
}

function removeTag(tag: string): void {
  const summary = props.summary
  if (!summary) {
    return
  }
  requestSave({
    key_topics: summary.key_topics.filter((topic) => topic !== tag),
  })
}

function requestSave(payload: DocumentSummaryUpdate, onSuccess?: () => void): void {
  isSavePending.value = true
  emit('save', payload, (saved) => {
    isSavePending.value = false
    if (saved) {
      onSuccess?.()
    }
  })
}

function parseLines(value: string): string[] {
  return uniqueStrings(
    value
      .split(/\r?\n|,/)
      .map((item) => item.trim()),
  )
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const normalized = value.trim()
    const key = normalized.toLocaleLowerCase()
    if (normalized && !seen.has(key)) {
      result.push(normalized)
      seen.add(key)
    }
  }
  return result
}

function cleanTag(value: string): string {
  return value.replace(/^#+/, '').replace(/\s+/g, ' ').trim()
}

function truncateMiddle(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLength) {
    return normalized
  }
  const edgeLength = Math.floor((maxLength - 1) / 2)
  return `${normalized.slice(0, edgeLength)}…${normalized.slice(-edgeLength)}`
}

function isSameText(first: string, second: string): boolean {
  return first.localeCompare(second, undefined, { sensitivity: 'accent' }) === 0
}
</script>

<template>
  <article class="document-summary-card">
    <header class="document-summary-head">
      <div class="document-summary-title">
        <span class="summary-icon"><AppIcon name="auto_awesome" /></span>
        <div>
          <h3>AI Executive Summary</h3>
          <p v-if="summary" :title="summary.document_title || summary.business_domain">
            {{ summaryTitle }}
          </p>
        </div>
      </div>
      <div class="summary-head-actions">
        <button
          type="button"
          class="summary-action-button"
          :disabled="isGenerating || isSavingSummary || !canGenerate"
          @click="emit('generate')"
        >
          <AppIcon :name="summary ? 'refresh' : 'bolt'" />
          {{ generateLabel }}
        </button>
        <button
          v-if="summary && !isEditing"
          type="button"
          class="summary-icon-button"
          :disabled="isSavingSummary || isGenerating"
          aria-label="Edit summary"
          title="Edit summary"
          @click="startEditing"
        >
          <AppIcon name="edit" />
        </button>
      </div>
    </header>

    <div v-if="summary && !isEditing" class="summary-view-layout">
      <section class="summary-main-panel">
        <div class="summary-section-head">
          <div>
            <span>Summary</span>
          </div>
        </div>
        <div class="summary-scroll-panel summary-text-panel">
          <p v-if="summaryText">{{ summaryText }}</p>
          <p v-else class="summary-placeholder">
            No executive summary text is available yet.
          </p>
        </div>
      </section>

      <aside class="summary-side-panel">
        <section class="summary-tags-panel">
          <div class="summary-section-head">
            <div>
              <span>Keywords & Tags</span>
              <strong>{{ primaryTags.length }}</strong>
            </div>
            <button
              v-if="!isAddingTag"
              type="button"
              class="summary-inline-button"
              :disabled="isSavingSummary"
              @click="openTagInput"
            >
              <AppIcon name="add" />
              Add
            </button>
          </div>
          <form v-if="isAddingTag" class="summary-tag-form" @submit.prevent="addTag">
            <input
              ref="newTagInput"
              v-model="newTagText"
              type="text"
              placeholder="Add a tag"
              @keydown.escape.prevent="cancelTagInput"
            />
            <button type="submit" :disabled="isSavingSummary">Save</button>
            <button type="button" :disabled="isSavingSummary" @click="cancelTagInput">Cancel</button>
          </form>
          <div class="summary-scroll-panel summary-tag-scroll">
            <button
              v-for="tag in primaryTags"
              :key="tag"
              type="button"
              class="summary-tag-pill"
              :aria-label="`Remove ${tag}`"
              :disabled="isSavingSummary"
              :title="`Remove ${tag}`"
              @click="removeTag(tag)"
            >
              <span>#{{ tag }}</span>
              <AppIcon name="close" />
            </button>
            <span v-if="primaryTags.length === 0" class="summary-placeholder">
              No tags yet.
            </span>
          </div>
        </section>

        <section class="summary-routing-panel">
          <div class="summary-section-head compact">
            <span>Routing Signals</span>
          </div>
          <div class="summary-scroll-panel summary-routing-scroll">
            <span v-for="tag in routingTags" :key="tag">{{ tag }}</span>
            <span v-if="routingTags.length === 0" class="summary-placeholder">
              No routing signals yet.
            </span>
          </div>
        </section>
      </aside>

      <section class="summary-question-grid">
        <div v-for="block in questionBlocks" :key="block.key" class="summary-question-panel">
          <div class="summary-section-head compact">
            <span><AppIcon :name="block.icon" />{{ block.title }}</span>
          </div>
          <div class="summary-scroll-panel summary-question-scroll">
            <p v-for="item in block.items" :key="item">{{ item }}</p>
            <p v-if="block.items.length === 0" class="summary-placeholder">
              No guidance available for this category.
            </p>
          </div>
        </div>
      </section>

      <section class="summary-sheet-section">
        <div class="summary-section-head">
          <div>
            <span>Sheet Notes</span>
            <strong>{{ sheetCount }}</strong>
          </div>
        </div>
        <div class="summary-sheet-scroll">
          <article
            v-for="sheet in sheetSummaries"
            :key="sheet.sheet_id"
            class="summary-sheet-card"
          >
            <header>
              <strong>{{ sheet.sheet_name || 'Untitled sheet' }}</strong>
              <span>{{ sheet.important_columns.length }} columns</span>
            </header>
            <div class="summary-sheet-text summary-scroll-panel">
              <p v-if="sheet.summary.trim()">{{ sheet.summary }}</p>
              <p v-else class="summary-placeholder">No sheet notes yet.</p>
            </div>
            <div v-if="sheet.important_columns.length > 0" class="summary-mini-tags">
              <span v-for="column in sheet.important_columns" :key="column">{{ column }}</span>
            </div>
          </article>
          <article v-if="sheetSummaries.length === 0" class="summary-sheet-card empty">
            <header>
              <strong>No sheet notes</strong>
              <span>0 columns</span>
            </header>
            <div class="summary-sheet-text summary-scroll-panel">
              <p class="summary-placeholder">Generate or edit the summary to add sheet-level notes.</p>
            </div>
          </article>
        </div>
      </section>
    </div>

    <form v-else-if="summary && isEditing" class="summary-edit-layout" @submit.prevent="saveDraft">
      <label class="summary-field full">
        <span>File Name</span>
        <input v-model="draftDocumentTitle" type="text" required maxlength="255" />
      </label>
      <label class="summary-field full">
        <span>Summary</span>
        <textarea v-model="draftSummaryText" rows="7" required></textarea>
      </label>
      <label class="summary-field">
        <span>Business Domain</span>
        <input v-model="draftBusinessDomain" type="text" required />
      </label>
      <label class="summary-field">
        <span>Tags</span>
        <textarea v-model="draftKeyTopicsText" rows="5"></textarea>
      </label>
      <label class="summary-field">
        <span>Good Questions</span>
        <textarea v-model="draftSuitableQuestionsText" rows="5"></textarea>
      </label>
      <label class="summary-field">
        <span>Out of Scope</span>
        <textarea v-model="draftUnsuitableQuestionsText" rows="5"></textarea>
      </label>
      <label class="summary-field full">
        <span>Routing Notes</span>
        <textarea v-model="draftRoutingNotes" rows="3"></textarea>
      </label>

      <section v-if="draftSheetSummaries.length > 0" class="summary-edit-sheets">
        <div class="summary-section-head">
          <div>
            <span>Sheet Notes</span>
            <strong>{{ draftSheetSummaries.length }}</strong>
          </div>
        </div>
        <div class="summary-edit-sheet-grid">
          <label
            v-for="sheet in draftSheetSummaries"
            :key="sheet.sheet_id"
            class="summary-field"
          >
            <span>{{ sheet.sheet_name }}</span>
            <textarea v-model="sheet.summary" rows="4" required></textarea>
          </label>
        </div>
      </section>

      <div class="summary-edit-actions">
        <button
          type="button"
          class="summary-action-button secondary"
          :disabled="isSavingSummary"
          @click="cancelEditing"
        >
          Cancel
        </button>
        <button
          type="submit"
          class="summary-action-button"
          :disabled="isSavingSummary || isGenerating"
        >
          <AppIcon name="save" />
          {{ isSavingSummary ? 'Saving...' : 'Save Summary' }}
        </button>
      </div>
    </form>

    <div v-else class="insight-empty-state document-summary-empty">
      <div class="insight-icon"><AppIcon name="auto_awesome" /></div>
      <h4>No summary generated</h4>
      <p>Select a file and generate a summary to see workbook-level routing context.</p>
      <button
        type="button"
        class="primary-action"
        :disabled="isGenerating || !canGenerate"
        @click="emit('generate')"
      >
        <AppIcon name="bolt" />
        {{ isGenerating ? 'Generating...' : 'Generate Summary' }}
      </button>
    </div>
  </article>
</template>
