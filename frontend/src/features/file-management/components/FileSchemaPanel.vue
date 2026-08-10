<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import BaseInsightSectionCard from '../../../shared/file-workspace/components/BaseInsightSectionCard.vue'
import BaseFileState from '../../../shared/file-workspace/components/BaseFileState.vue'
import { shortId } from '../../../app/workspace-utils'

import type { ExcelFile, ExcelFileVersion, ExcelSheet } from '../../../types/excel-assets'
import type { FileSchemaColumn } from '../types'

defineProps<{
  selectedFile: ExcelFile | null
  selectedVersion: ExcelFileVersion | null
  selectedVersionId: string
  sheets: ExcelSheet[]
  selectedSheetId: string
  selectedSheet: ExcelSheet | null
  workbookRowCount: number
  schemaColumns: FileSchemaColumn[]
  disabled: boolean
}>()

const emit = defineEmits<{
  selectSheet: [sheet: ExcelSheet]
}>()
</script>

<template>
  <BaseInsightSectionCard
    title="Schema"
    icon-name="schema"
    :meta="`${schemaColumns.length} fields`"
    tone="premium"
  >
  <section class="file-schema-panel">
    <article class="schema-overview-card">
      <div class="schema-card-head">
        <div>
          <AppIcon name="schema" />
          <h3>{{ selectedFile?.display_name ?? 'No workbook selected' }}</h3>
        </div>
        <span>{{ selectedVersion?.status ?? 'No version' }}</span>
      </div>
      <div class="schema-metrics">
        <div>
          <span>Version</span>
          <strong>{{ shortId(selectedVersionId) }}</strong>
        </div>
        <div>
          <span>Sheets</span>
          <strong>{{ sheets.length }}</strong>
        </div>
        <div>
          <span>Rows</span>
          <strong>{{ workbookRowCount }}</strong>
        </div>
        <div>
          <span>Columns</span>
          <strong>{{ selectedSheet?.column_count ?? 0 }}</strong>
        </div>
      </div>
    </article>

    <article class="schema-sheet-card">
      <div class="schema-card-head">
        <div>
          <AppIcon name="view_week" />
          <h3>Workbook Sheets</h3>
        </div>
      </div>
      <div class="schema-sheet-list">
        <button
          v-for="sheet in sheets"
          :key="sheet.sheet_id"
          type="button"
          :class="{ active: sheet.sheet_id === selectedSheetId }"
          :disabled="disabled"
          @click="emit('selectSheet', sheet)"
        >
          <strong>{{ sheet.sheet_code }} {{ sheet.sheet_name }}</strong>
          <span>{{ sheet.row_count }} rows / {{ sheet.column_count }} columns</span>
        </button>
        <BaseFileState
          v-if="sheets.length === 0"
          domain="excel"
          icon-name="table_rows"
          title="No sheets available"
          detail="Select a workbook with parsed sheets to inspect its schema."
        />
      </div>
    </article>

    <article class="schema-column-card">
      <div class="schema-card-head">
        <div>
          <AppIcon name="table_rows" />
          <h3>{{ selectedSheet?.sheet_name ?? 'Columns' }}</h3>
        </div>
      </div>
      <div class="schema-column-list">
        <div v-for="column in schemaColumns" :key="column.key" class="schema-column-row">
          <strong>{{ column.label }}</strong>
          <span>{{ column.sourceName }}</span>
          <em>{{ column.type }}</em>
          <small>{{ column.sample }}</small>
        </div>
        <BaseFileState
          v-if="schemaColumns.length === 0"
          domain="excel"
          icon-name="schema"
          title="No columns available"
          detail="Select a sheet to inspect its columns."
        />
      </div>
    </article>
  </section>
  </BaseInsightSectionCard>
</template>
