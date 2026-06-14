<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import SheetSearchResults from '../../../components/SheetSearchResults.vue'
import { rowDomId, shortId } from '../../../app/workspace-utils'

import type {
  ExcelFileVersion,
  ExcelSheet,
  RowLookupResponse,
  SheetPreviewResponse,
  SheetSearchMatch,
} from '../../../types/excel-assets'

defineProps<{
  versions: ExcelFileVersion[]
  selectedVersionId: string
  sheets: ExcelSheet[]
  selectedSheetId: string
  selectedSheet: ExcelSheet | null
  disabled: boolean
  sheetSearchTerm: string
  isSheetSearchLoading: boolean
  workbookRowCount: number
  previewRangeLabel: string
  rowLookup: RowLookupResponse | null
  sheetSearchSummary: string
  sheetSearchResults: SheetSearchMatch[]
  sheetSearchTotal: number
  sheetSearchError: string
  isLookupLoading: boolean
  preview: SheetPreviewResponse | null
  previewHeaders: string[]
  previewLimit: number
  canPreviewPrevious: boolean
  canPreviewNext: boolean
  rowIsHighlighted: (row: string[]) => boolean
  isSheetSearchMatchedCell: (row: string[], columnIndex: number) => boolean
}>()

const emit = defineEmits<{
  versionChange: [versionId: string]
  sheetChange: [sheetId: string]
  sheetSearchTermChange: [term: string]
  submitSheetSearch: []
  selectSearchMatch: [match: SheetSearchMatch]
  lookupRow: [row: string[]]
  loadPreviewOffset: [offset: number]
  selectSheet: [sheet: ExcelSheet]
}>()

function readSelectValue(event: Event): string {
  return event.target instanceof HTMLSelectElement ? event.target.value : ''
}

function readInputValue(event: Event): string {
  return event.target instanceof HTMLInputElement ? event.target.value : ''
}
</script>

<template>
  <section class="file-preview-panel">
    <div class="file-preview-controls">
      <label>
        <span>Version</span>
        <select
          :value="selectedVersionId"
          :disabled="versions.length === 0 || disabled"
          @change="emit('versionChange', readSelectValue($event))"
        >
          <option value="">Version</option>
          <option
            v-for="version in versions"
            :key="version.version_id"
            :value="version.version_id"
          >
            {{ version.status }} - {{ shortId(version.version_id) }}
          </option>
        </select>
      </label>
      <label>
        <span>Sheet</span>
        <select
          :value="selectedSheetId"
          :disabled="sheets.length === 0 || disabled"
          @change="emit('sheetChange', readSelectValue($event))"
        >
          <option value="">Sheet</option>
          <option v-for="sheet in sheets" :key="sheet.sheet_id" :value="sheet.sheet_id">
            {{ sheet.sheet_code }} {{ sheet.sheet_name }}
          </option>
        </select>
      </label>
      <form class="preview-search-control" @submit.prevent="emit('submitSheetSearch')">
        <span>Search data</span>
        <div class="inline-control">
          <input
            :value="sheetSearchTerm"
            placeholder="Keyword"
            type="search"
            :disabled="!selectedVersionId || disabled"
            @input="emit('sheetSearchTermChange', readInputValue($event))"
          />
          <button
            type="submit"
            aria-label="Search data"
            :disabled="isSheetSearchLoading || !selectedVersionId || disabled"
          >
            <AppIcon name="search" />
          </button>
        </div>
      </form>
    </div>

    <div class="preview-metrics">
      <div>
        <span>Sheets</span>
        <strong>{{ sheets.length }}</strong>
      </div>
      <div>
        <span>Rows</span>
        <strong>{{ workbookRowCount }}</strong>
      </div>
      <div>
        <span>Visible</span>
        <strong>{{ previewRangeLabel }}</strong>
      </div>
      <div>
        <span>Highlighted</span>
        <strong>{{ rowLookup?.mapping.row_id ?? '-' }}</strong>
      </div>
    </div>

    <div
      v-if="rowLookup || sheetSearchSummary || sheetSearchResults.length > 0"
      class="preview-feedback-stack"
    >
      <section v-if="rowLookup" class="evidence-strip compact">
        <div>
          <p class="eyebrow">Highlighted Evidence</p>
          <h3>{{ rowLookup.mapping.row_id }}</h3>
        </div>
        <p>
          {{ rowLookup.sheet.sheet_name }} / original row
          {{ rowLookup.mapping.original_row_number }}
        </p>
      </section>

      <SheetSearchResults
        v-if="sheetSearchSummary || sheetSearchResults.length > 0"
        variant="file-preview"
        :summary="sheetSearchSummary"
        :matches="sheetSearchResults"
        :total-matches="sheetSearchTotal"
        :active-row-id="rowLookup?.mapping.row_id ?? ''"
        :has-error="Boolean(sheetSearchError)"
        :disabled="isLookupLoading || disabled"
        @select="emit('selectSearchMatch', $event)"
      />
    </div>

    <section class="spreadsheet-card preview-card">
      <div class="spreadsheet-header">
        <div>
          <strong>{{ selectedSheet?.sheet_name ?? 'Sheet preview' }}</strong>
          <span>{{ previewRangeLabel }}</span>
        </div>
        <div class="pagination-actions">
          <button
            type="button"
            class="secondary-button"
            :disabled="!canPreviewPrevious || disabled"
            @click="emit('loadPreviewOffset', (preview?.offset ?? 0) - previewLimit)"
          >
            Previous
          </button>
          <button
            type="button"
            class="secondary-button"
            :disabled="!canPreviewNext || disabled"
            @click="emit('loadPreviewOffset', (preview?.offset ?? 0) + previewLimit)"
          >
            Next
          </button>
        </div>
      </div>

      <div v-if="preview" class="excel-scroll">
        <table class="excel-table">
          <thead>
            <tr>
              <th v-for="header in previewHeaders" :key="header">{{ header }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, rowIndex) in preview.rows"
              :id="rowDomId(row[0])"
              :key="`${row[0]}-${preview.offset}-${rowIndex}`"
              :class="{
                highlighted: rowIsHighlighted(row),
                'header-like': preview.offset === 0 && rowIndex === 0,
              }"
              @click="emit('lookupRow', row)"
            >
              <td
                v-for="(cell, cellIndex) in row"
                :key="`${row[0]}-${cellIndex}`"
                :class="{ 'search-match': isSheetSearchMatchedCell(row, cellIndex) }"
              >
                {{ cell || '-' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state">
        Upload or select a workbook to preview its rows.
      </div>
    </section>

    <div class="sheet-tabs compact" aria-label="Workbook sheets">
      <button
        v-for="sheet in sheets"
        :key="sheet.sheet_id"
        type="button"
        :class="{ active: sheet.sheet_id === selectedSheetId }"
        :disabled="disabled"
        @click="emit('selectSheet', sheet)"
      >
        {{ sheet.sheet_name }}
      </button>
    </div>
  </section>
</template>
