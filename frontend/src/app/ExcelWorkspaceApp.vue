<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'

import {
  deleteExcelFile,
  ExcelWorkspaceApiError,
  listExcelFiles,
  listExcelSheets,
  listExcelVersions,
  lookupExcelRow,
  previewExcelSheet,
  uploadExcelFile,
} from '../api/excel-assets-api'
import { generateDocumentSummary, getDocumentSummary } from '../api/document-summaries-api'
import { getLlmModelOptions } from '../api/llm-api'
import ChatPanel from '../components/ChatPanel.vue'
import type { ChatAnswer, ChatRouteResult, ExcelCitation, SelectedDocument } from '../types/chat'
import type { DocumentSummary } from '../types/document-summary'
import type { LlmModelDefaults, LlmProviderOption } from '../types/llm'
import type {
  ExcelFile,
  ExcelFileVersion,
  ExcelSheet,
  RowLookupResponse,
  SheetPreviewResponse,
} from '../types/excel-assets'

type ActiveView = 'files' | 'chat'

const previewLimit = 250
const allowedUploadExtensions = ['.xls', '.xlsx', '.xlsm', '.xltx', '.xltm']

const activeView = ref<ActiveView>('files')
const files = ref<ExcelFile[]>([])
const versions = ref<ExcelFileVersion[]>([])
const sheets = ref<ExcelSheet[]>([])
const preview = ref<SheetPreviewResponse | null>(null)
const rowLookup = ref<RowLookupResponse | null>(null)
const documentSummary = ref<DocumentSummary | null>(null)
const latestRoute = ref<ChatRouteResult | null>(null)
const latestAnswer = ref<ChatAnswer | null>(null)
const selectedFileId = ref<string>('')
const selectedVersionId = ref<string>('')
const selectedSheetId = ref<string>('')
const selectedUploadFile = ref<File | null>(null)
const pendingReplaceFile = ref<File | null>(null)
const pendingDeleteFile = ref<ExcelFile | null>(null)
const lookupRowId = ref<string>('')
const statusMessage = ref<string>('Ready')
const errorMessage = ref<string>('')
const searchTerm = ref<string>('')
const isBusy = ref<boolean>(false)
const isSummaryLoading = ref<boolean>(false)
const isLookupLoading = ref<boolean>(false)
const isDraggingUpload = ref<boolean>(false)
const fileInput = ref<HTMLInputElement | null>(null)
const availableLlmModels = ref<string[]>([])
const availableLlmProviders = ref<LlmProviderOption[]>([])
const summaryProvider = ref<string>('siliconflow')
const summaryModel = ref<string>('')
const routerProvider = ref<string>('siliconflow')
const routerModel = ref<string>('')
const answerProvider = ref<string>('siliconflow')
const answerModel = ref<string>('')

const selectedFile = computed(() => {
  return files.value.find((file) => file.file_id === selectedFileId.value) ?? null
})

const activeVersion = computed(() => {
  return versions.value.find((version) => version.version_id === selectedVersionId.value) ?? null
})

const selectedSheet = computed(() => {
  return sheets.value.find((sheet) => sheet.sheet_id === selectedSheetId.value) ?? null
})

const filteredFiles = computed(() => {
  const query = searchTerm.value.trim().toLowerCase()
  if (!query) {
    return files.value
  }
  return files.value.filter((file) => file.display_name.toLowerCase().includes(query))
})

const previewHeaders = computed(() => {
  const widestRow = preview.value?.rows.reduce((width, row) => Math.max(width, row.length), 0) ?? 0
  return Array.from({ length: widestRow }, (_value, index) =>
    index === 0 ? '_id' : columnLabel(index),
  )
})

const workbookRowCount = computed(() => {
  return sheets.value.reduce((total, sheet) => total + sheet.row_count, 0)
})

const canPreviewPrevious = computed(() => {
  return (preview.value?.offset ?? 0) > 0
})

const canPreviewNext = computed(() => {
  if (!preview.value) {
    return false
  }
  return preview.value.offset + preview.value.rows.length < preview.value.total_rows
})

const previewRangeLabel = computed(() => {
  if (!preview.value || preview.value.total_rows === 0) {
    return '0 rows'
  }
  const start = preview.value.offset + 1
  const end = preview.value.offset + preview.value.rows.length
  return `${start}-${end} of ${preview.value.total_rows}`
})

const referencedDocuments = computed(() => {
  return latestAnswer.value?.selected_documents ?? latestRoute.value?.selected_documents ?? []
})

onMounted(() => {
  void initializeWorkspace()
})

async function initializeWorkspace(): Promise<void> {
  await loadLlmModelOptions()
  await refreshFiles()
}

async function loadLlmModelOptions(): Promise<void> {
  const options = await getLlmModelOptions()
  availableLlmModels.value = options.models
  availableLlmProviders.value = options.providers
  applyModelDefaults(options.defaults)
}

function applyModelDefaults(defaults: LlmModelDefaults): void {
  summaryProvider.value = defaults.summary_provider
  summaryModel.value = defaults.summary_model
  routerProvider.value = defaults.router_provider
  routerModel.value = defaults.router_model
  answerProvider.value = defaults.answer_provider
  answerModel.value = defaults.answer_model
  ensureStageModel('summary')
  ensureStageModel('router')
  ensureStageModel('answer')
}

async function refreshFiles(): Promise<void> {
  errorMessage.value = ''
  isBusy.value = true
  try {
    files.value = await listExcelFiles()
    const selectedStillExists = files.value.some((file) => file.file_id === selectedFileId.value)
    if (!selectedStillExists) {
      clearSelection()
    }
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0])
    }
    statusMessage.value = `${files.value.length} workbook${files.value.length === 1 ? '' : 's'} loaded`
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

async function chooseFile(file: ExcelFile, view: ActiveView | null = null): Promise<void> {
  errorMessage.value = ''
  isBusy.value = true
  try {
    await selectFile(file)
    if (view) {
      activeView.value = view
    }
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

async function selectFile(file: ExcelFile): Promise<void> {
  selectedFileId.value = file.file_id
  selectedVersionId.value = ''
  selectedSheetId.value = ''
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  versions.value = await listExcelVersions(file.file_id)
  const targetVersionId = file.active_version_id ?? versions.value[0]?.version_id ?? ''
  if (targetVersionId) {
    await selectVersion(targetVersionId)
  } else {
    sheets.value = []
  }
}

async function selectVersion(versionId: string): Promise<void> {
  if (!versionId) {
    selectedVersionId.value = ''
    sheets.value = []
    preview.value = null
    rowLookup.value = null
    documentSummary.value = null
    return
  }
  selectedVersionId.value = versionId
  selectedSheetId.value = ''
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  sheets.value = await listExcelSheets(versionId)
  await loadExistingSummary(versionId)
  if (sheets.value[0]) {
    await selectSheet(sheets.value[0])
  }
}

async function selectCurrentVersion(): Promise<void> {
  if (selectedVersionId.value) {
    await runInteraction(() => selectVersion(selectedVersionId.value))
  }
}

async function selectCurrentSheet(): Promise<void> {
  const sheet = sheets.value.find((item) => item.sheet_id === selectedSheetId.value)
  if (sheet) {
    await runInteraction(() => selectSheet(sheet))
  }
}

async function selectSheet(sheet: ExcelSheet): Promise<void> {
  selectedSheetId.value = sheet.sheet_id
  rowLookup.value = null
  lookupRowId.value = ''
  preview.value = await previewExcelSheet(sheet.sheet_id, 0, previewLimit)
}

async function loadPreviewPage(offset: number): Promise<void> {
  if (!selectedSheetId.value) {
    return
  }
  errorMessage.value = ''
  try {
    const safeOffset = Math.max(0, offset)
    preview.value = await previewExcelSheet(selectedSheetId.value, safeOffset, previewLimit)
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  }
}

async function loadExistingSummary(versionId: string): Promise<void> {
  try {
    documentSummary.value = await getDocumentSummary(versionId)
  } catch {
    documentSummary.value = null
  }
}

async function generateSummaryForSelectedVersion(): Promise<void> {
  if (!selectedVersionId.value) {
    errorMessage.value = 'Select a version first.'
    return
  }
  errorMessage.value = ''
  isSummaryLoading.value = true
  try {
    documentSummary.value = await generateDocumentSummary(
      selectedVersionId.value,
      summaryModel.value || null,
      summaryProvider.value || null,
    )
    statusMessage.value = 'Document description generated'
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isSummaryLoading.value = false
  }
}

function openUploadDialog(): void {
  fileInput.value?.click()
}

function handleUploadFileChange(event: Event): void {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  setUploadFile(input.files?.[0] ?? null)
}

function handleUploadDrop(event: DragEvent): void {
  isDraggingUpload.value = false
  setUploadFile(event.dataTransfer?.files[0] ?? null)
}

function setUploadFile(file: File | null): void {
  pendingReplaceFile.value = null
  if (!file) {
    selectedUploadFile.value = null
    return
  }
  if (!isAllowedUploadFile(file)) {
    selectedUploadFile.value = null
    errorMessage.value = 'Only Excel workbooks are supported: .xls, .xlsx, .xlsm, .xltx, .xltm.'
    return
  }
  errorMessage.value = ''
  selectedUploadFile.value = file
  statusMessage.value = `${file.name} is ready to upload`
}

function requestDeleteFile(file: ExcelFile): void {
  pendingDeleteFile.value = file
  errorMessage.value = ''
  statusMessage.value = `Confirm deletion for ${file.display_name}. This will permanently remove all related versions, artifacts, summaries, and chat attachments.`
}

function cancelDeleteFile(): void {
  pendingDeleteFile.value = null
  statusMessage.value = 'Deletion cancelled.'
}

async function confirmDeleteFile(): Promise<void> {
  const file = pendingDeleteFile.value
  if (!file) {
    return
  }

  errorMessage.value = ''
  isBusy.value = true
  try {
    const result = await deleteExcelFile(file.file_id, true)
    pendingDeleteFile.value = null
    if (selectedFileId.value === file.file_id) {
      clearSelection()
    }
    files.value = await listExcelFiles()
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0])
    }
    statusMessage.value =
      `${result.display_name} deleted. Removed ${result.deleted_versions} version(s), ${result.deleted_sheets} sheet(s), ${result.deleted_artifacts} artifact(s), ${result.deleted_summaries} summary record(s), and ${result.deleted_chat_session_documents} chat attachment(s).`
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingDeleteFile.value = file
      statusMessage.value = `Confirm deletion for ${file.display_name}.`
      return
    }
    errorMessage.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

async function uploadSelectedFile(replaceExisting = false): Promise<void> {
  const file = replaceExisting ? pendingReplaceFile.value : selectedUploadFile.value
  if (!file) {
    errorMessage.value = 'Choose an Excel workbook first.'
    return
  }

  errorMessage.value = ''
  isBusy.value = true
  try {
    const result = await uploadExcelFile(file, replaceExisting)
    pendingReplaceFile.value = null
    selectedUploadFile.value = null
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    statusMessage.value = `${result.file.display_name} uploaded and parsed`
    files.value = await listExcelFiles()
    const uploadedFile = files.value.find((item) => item.file_id === result.file.file_id)
    if (uploadedFile) {
      await selectFile(uploadedFile)
    }
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingReplaceFile.value = file
      selectedUploadFile.value = null
      errorMessage.value = ''
      statusMessage.value = 'A workbook with this name exists. Confirm replacement to create a new version.'
      return
    }
    errorMessage.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

async function lookupRow(): Promise<void> {
  if (!selectedSheetId.value || !lookupRowId.value.trim()) {
    errorMessage.value = 'Enter a row id such as S001_R25.'
    return
  }
  await lookupRowInSheet(selectedSheetId.value, lookupRowId.value.trim())
}

async function lookupVisibleRow(row: string[]): Promise<void> {
  const rowId = row[0]?.trim()
  if (!rowId || isLookupLoading.value) {
    return
  }
  lookupRowId.value = rowId
  await lookupRow()
}

async function lookupRowInSheet(sheetId: string, rowId: string): Promise<void> {
  errorMessage.value = ''
  isLookupLoading.value = true
  try {
    const result = await lookupExcelRow(sheetId, rowId)
    rowLookup.value = result
    await ensureLookupRowVisible(result)
    await nextTick()
    document.getElementById(rowDomId(result.mapping.row_id))?.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    })
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isLookupLoading.value = false
  }
}

async function ensureLookupRowVisible(result: RowLookupResponse): Promise<void> {
  const rowZeroIndex = Math.max(0, result.mapping.raw_csv_row_number - 1)
  const currentOffset = preview.value?.offset ?? 0
  const currentEnd = currentOffset + (preview.value?.rows.length ?? 0)
  const isCurrentSheetPreview = preview.value?.sheet.sheet_id === result.sheet.sheet_id
  if (!isCurrentSheetPreview || rowZeroIndex < currentOffset || rowZeroIndex >= currentEnd) {
    const centeredOffset = Math.max(0, rowZeroIndex - 24)
    preview.value = await previewExcelSheet(result.sheet.sheet_id, centeredOffset, previewLimit)
  }
}

async function handleCitationSelected(citation: ExcelCitation): Promise<void> {
  activeView.value = 'chat'
  errorMessage.value = ''
  try {
    let targetFile = files.value.find((file) => file.file_id === citation.file_id)
    if (!targetFile) {
      files.value = await listExcelFiles()
      targetFile = files.value.find((file) => file.file_id === citation.file_id)
    }
    if (targetFile && selectedFileId.value !== targetFile.file_id) {
      await selectFile(targetFile)
    }
    if (selectedVersionId.value !== citation.version_id) {
      await selectVersion(citation.version_id)
    }
    const targetSheet = sheets.value.find((sheet) => sheet.sheet_id === citation.sheet_id)
    if (targetSheet && selectedSheetId.value !== targetSheet.sheet_id) {
      await selectSheet(targetSheet)
    }
    lookupRowId.value = citation.row_id
    await lookupRowInSheet(citation.sheet_id, citation.row_id)
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  }
}

function handleChatAnswer(answer: ChatAnswer): void {
  latestAnswer.value = answer
}

function handleChatRoute(route: ChatRouteResult): void {
  latestRoute.value = route
  latestAnswer.value = null
}

async function openReferencedDocument(document: SelectedDocument): Promise<void> {
  const file = files.value.find((item) => item.file_id === document.file_id)
  if (file) {
    await chooseFile(file, 'chat')
  }
  if (selectedVersionId.value !== document.version_id) {
    await runInteraction(() => selectVersion(document.version_id))
  }
}

async function runInteraction(action: () => Promise<void>): Promise<void> {
  errorMessage.value = ''
  isBusy.value = true
  try {
    await action()
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

function clearSelection(): void {
  selectedFileId.value = ''
  selectedVersionId.value = ''
  selectedSheetId.value = ''
  versions.value = []
  sheets.value = []
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
}

function rowIsHighlighted(row: string[]): boolean {
  return Boolean(rowLookup.value && row[0] === rowLookup.value.mapping.row_id)
}

function rowDomId(rowId: string): string {
  return `excel-row-${rowId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

function isAllowedUploadFile(file: File): boolean {
  const name = file.name.toLowerCase()
  return allowedUploadExtensions.some((extension) => name.endsWith(extension))
}

function fileTypeLabel(file: ExcelFile): string {
  const extension = file.display_name.split('.').pop()?.toLowerCase()
  if (!extension) {
    return 'Excel'
  }
  return extension.includes('xls') ? 'Excel' : extension.toUpperCase()
}

function fileStatusLabel(file: ExcelFile): string {
  if (file.file_id === selectedFileId.value && activeVersion.value) {
    return activeVersion.value.status
  }
  return file.active_version_id ? 'ready' : 'pending'
}

function fileDisplayName(fileId: string): string {
  return files.value.find((file) => file.file_id === fileId)?.display_name ?? shortId(fileId)
}

function selectedDocumentTitle(document: SelectedDocument): string {
  return fileDisplayName(document.file_id)
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function shortId(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function confidenceLabel(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return '-'
  }
  return `${Math.round(value * 100)}%`
}

function modelsForProvider(provider: string): string[] {
  return availableLlmProviders.value.find((item) => item.provider === provider)?.models ?? []
}

function ensureStageModel(stage: 'summary' | 'router' | 'answer'): void {
  const provider =
    stage === 'summary'
      ? summaryProvider.value
      : stage === 'router'
        ? routerProvider.value
        : answerProvider.value
  const models = modelsForProvider(provider)
  if (stage === 'summary' && !models.includes(summaryModel.value)) {
    summaryModel.value = models[0] ?? ''
  }
  if (stage === 'router' && !models.includes(routerModel.value)) {
    routerModel.value = models[0] ?? ''
  }
  if (stage === 'answer' && !models.includes(answerModel.value)) {
    answerModel.value = models[0] ?? ''
  }
}

function columnLabel(index: number): string {
  let value = index
  let label = ''
  while (value > 0) {
    const remainder = (value - 1) % 26
    label = String.fromCharCode(65 + remainder) + label
    value = Math.floor((value - 1) / 26)
  }
  return label
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected error.'
}
</script>

<template>
  <main class="excelai-app">
    <aside class="app-sidebar">
      <div class="brand-block">
        <h1>ExcelAI</h1>
        <p>Data Analyst Pro</p>
      </div>

      <nav class="primary-nav" aria-label="Primary">
        <button
          type="button"
          class="nav-item"
          :class="{ active: activeView === 'files' }"
          @click="activeView = 'files'"
        >
          <span class="nav-glyph">F</span>
          <span>Files</span>
        </button>
        <button
          type="button"
          class="nav-item"
          :class="{ active: activeView === 'chat' }"
          @click="activeView = 'chat'"
        >
          <span class="nav-glyph">C</span>
          <span>Chat</span>
        </button>
        <button type="button" class="nav-item muted-nav" disabled>
          <span class="nav-glyph">H</span>
          <span>History</span>
        </button>
        <button type="button" class="nav-item muted-nav" disabled>
          <span class="nav-glyph">S</span>
          <span>Settings</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button type="button" class="primary-action" :disabled="isBusy" @click="refreshFiles">
          Refresh Files
        </button>
        <div class="user-mini">
          <div class="avatar">A</div>
          <div>
            <strong>Professional User</strong>
            <span>Local workspace</span>
          </div>
        </div>
      </div>
    </aside>

    <section class="app-main">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ activeView === 'files' ? 'Knowledge Base' : 'Conversation' }}</p>
          <h2>{{ activeView === 'files' ? 'File Management' : 'Excel Analysis' }}</h2>
        </div>
        <div class="topbar-actions">
          <label class="search-field">
            <span>Search</span>
            <input v-model="searchTerm" type="search" placeholder="Search workbooks..." />
          </label>
          <button type="button" class="view-switch" @click="activeView = activeView === 'files' ? 'chat' : 'files'">
            {{ activeView === 'files' ? 'Open Chat' : 'Manage Files' }}
          </button>
        </div>
      </header>

      <div v-if="statusMessage || errorMessage" class="notice-row">
        <p v-if="statusMessage" class="status-note">{{ statusMessage }}</p>
        <p v-if="errorMessage" class="error-note">{{ errorMessage }}</p>
      </div>

      <section v-if="activeView === 'files'" class="file-page">
        <section
          class="upload-card"
          :class="{ dragging: isDraggingUpload }"
          @click="openUploadDialog"
          @dragover.prevent="isDraggingUpload = true"
          @dragleave.prevent="isDraggingUpload = false"
          @drop.prevent="handleUploadDrop"
        >
          <input
            ref="fileInput"
            class="visually-hidden"
            type="file"
            accept=".xls,.xlsx,.xlsm,.xltx,.xltm"
            @change="handleUploadFileChange"
          />
          <div class="upload-icon">UP</div>
          <div class="upload-copy">
            <h3>Upload Excel Workbook</h3>
            <p>
              <button type="button" class="link-button" @click.stop="openUploadDialog">Browse</button>
              Excel workbook files.
            </p>
          </div>
          <div class="format-pills">
            <span>.xlsx</span>
            <span>.xls</span>
            <span>.xlsm</span>
          </div>
        </section>

        <section v-if="selectedUploadFile || pendingReplaceFile" class="upload-queue">
          <div>
            <p class="eyebrow">Pending Upload</p>
            <h3>{{ pendingReplaceFile?.name ?? selectedUploadFile?.name }}</h3>
          </div>
          <div v-if="pendingReplaceFile" class="replace-actions">
            <p>This filename already exists. Replacement will create a new active version.</p>
            <button type="button" class="danger-subtle" :disabled="isBusy" @click="uploadSelectedFile(true)">
              Confirm Replacement
            </button>
            <button type="button" class="secondary-button" @click="pendingReplaceFile = null">Cancel</button>
          </div>
          <button
            v-else
            type="button"
            class="primary-action"
            :disabled="isBusy || !selectedUploadFile"
            @click="uploadSelectedFile(false)"
          >
            Upload and Parse
          </button>
        </section>

        <section v-if="pendingDeleteFile" class="upload-queue">
          <div>
            <p class="eyebrow">Pending Delete</p>
            <h3>{{ pendingDeleteFile.display_name }}</h3>
          </div>
          <div class="replace-actions">
            <p>
              This will permanently delete the workbook and all related versions, artifacts,
              profiles, summaries, row mappings, and chat document attachments.
            </p>
            <button type="button" class="danger-subtle" :disabled="isBusy" @click="confirmDeleteFile">
              Confirm Delete
            </button>
            <button type="button" class="secondary-button" :disabled="isBusy" @click="cancelDeleteFile">
              Cancel
            </button>
          </div>
        </section>

        <section class="file-table-card">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">Workbooks</p>
              <h3>{{ filteredFiles.length }} files</h3>
            </div>
            <button type="button" class="secondary-button" :disabled="isBusy" @click="refreshFiles">
              Refresh
            </button>
          </div>

          <div class="table-wrap">
            <table class="file-table">
              <thead>
                <tr>
                  <th>File Name</th>
                  <th>Type</th>
                  <th>Active Version</th>
                  <th>Updated</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="file in filteredFiles"
                  :key="file.file_id"
                  class="file-row"
                  :class="{ selected: file.file_id === selectedFileId }"
                  @click="chooseFile(file)"
                >
                  <td>
                    <div class="file-name-cell">
                      <span class="file-badge">XL</span>
                      <strong>{{ file.display_name }}</strong>
                    </div>
                  </td>
                  <td>{{ fileTypeLabel(file) }}</td>
                  <td class="mono">{{ shortId(file.active_version_id) }}</td>
                  <td>{{ formatDate(file.updated_at) }}</td>
                  <td>
                    <span class="status-pill" :class="fileStatusLabel(file)">
                      {{ fileStatusLabel(file) }}
                    </span>
                  </td>
                  <td class="row-actions">
                    <button type="button" class="icon-text-button" @click.stop="chooseFile(file, 'chat')">
                      Open
                    </button>
                    <button type="button" class="icon-text-button danger-text" @click.stop="requestDeleteFile(file)">
                      Delete
                    </button>
                  </td>
                </tr>
                <tr v-if="filteredFiles.length === 0">
                  <td colspan="6" class="empty-cell">No matching workbooks.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="file-detail-grid">
          <article class="workbook-overview">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">Selected Workbook</p>
                <h3>{{ selectedFile?.display_name ?? 'No workbook selected' }}</h3>
              </div>
              <button
                type="button"
                class="secondary-button"
                :disabled="!selectedFile"
                @click="activeView = 'chat'"
              >
                Analyze
              </button>
            </div>

            <div v-if="availableLlmProviders.length > 0" class="model-config-card">
              <div class="panel-heading">
                <div>
                  <p class="eyebrow">LLM Settings</p>
                  <h3>Stage Providers</h3>
                </div>
              </div>
              <div class="model-config-grid">
                <div class="model-stage-control">
                  <label>
                    <span>Summary Provider</span>
                    <select v-model="summaryProvider" @change="ensureStageModel('summary')">
                      <option
                        v-for="provider in availableLlmProviders"
                        :key="`summary-provider-${provider.provider}`"
                        :value="provider.provider"
                      >
                        {{ provider.label }}
                      </option>
                    </select>
                  </label>
                  <label>
                    <span>Summary Model</span>
                    <select v-model="summaryModel">
                      <option v-for="model in modelsForProvider(summaryProvider)" :key="`summary-${model}`" :value="model">
                        {{ model }}
                      </option>
                    </select>
                  </label>
                </div>
                <div class="model-stage-control">
                  <label>
                    <span>Router Provider</span>
                    <select v-model="routerProvider" @change="ensureStageModel('router')">
                      <option
                        v-for="provider in availableLlmProviders"
                        :key="`router-provider-${provider.provider}`"
                        :value="provider.provider"
                      >
                        {{ provider.label }}
                      </option>
                    </select>
                  </label>
                  <label>
                    <span>Router Model</span>
                    <select v-model="routerModel">
                      <option v-for="model in modelsForProvider(routerProvider)" :key="`router-${model}`" :value="model">
                        {{ model }}
                      </option>
                    </select>
                  </label>
                </div>
                <div class="model-stage-control">
                  <label>
                    <span>Answer Provider</span>
                    <select v-model="answerProvider" @change="ensureStageModel('answer')">
                      <option
                        v-for="provider in availableLlmProviders"
                        :key="`answer-provider-${provider.provider}`"
                        :value="provider.provider"
                      >
                        {{ provider.label }}
                      </option>
                    </select>
                  </label>
                  <label>
                    <span>Answer Model</span>
                    <select v-model="answerModel">
                      <option v-for="model in modelsForProvider(answerProvider)" :key="`answer-${model}`" :value="model">
                        {{ model }}
                      </option>
                    </select>
                  </label>
                </div>
              </div>
            </div>

            <div class="metric-grid">
              <div>
                <span>Versions</span>
                <strong>{{ versions.length }}</strong>
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
                <span>Active</span>
                <strong>{{ activeVersion?.status ?? '-' }}</strong>
              </div>
            </div>

            <div class="form-grid compact">
              <label>
                <span>Version</span>
                <select v-model="selectedVersionId" :disabled="versions.length === 0" @change="selectCurrentVersion">
                  <option value="">Select version</option>
                  <option v-for="version in versions" :key="version.version_id" :value="version.version_id">
                    {{ version.status }} - {{ formatDate(version.created_at) }}
                  </option>
                </select>
              </label>
              <label>
                <span>Sheet</span>
                <select v-model="selectedSheetId" :disabled="sheets.length === 0" @change="selectCurrentSheet">
                  <option value="">Select sheet</option>
                  <option v-for="sheet in sheets" :key="sheet.sheet_id" :value="sheet.sheet_id">
                    {{ sheet.sheet_code }} {{ sheet.sheet_name }}
                  </option>
                </select>
              </label>
            </div>
          </article>

          <article class="document-summary-card">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">Document Description</p>
                <h3>{{ documentSummary?.business_domain || 'Model-generated profile' }}</h3>
              </div>
              <button
                type="button"
                class="primary-action"
                :disabled="isSummaryLoading || !selectedVersionId"
                @click="generateSummaryForSelectedVersion"
              >
                {{ isSummaryLoading ? 'Generating...' : 'Generate' }}
              </button>
            </div>

            <p v-if="documentSummary" class="summary-text">{{ documentSummary.summary_text }}</p>
            <p v-else class="empty-copy">No document description yet.</p>

            <div v-if="documentSummary" class="topic-list">
              <span v-for="topic in documentSummary.key_topics" :key="topic">{{ topic }}</span>
            </div>
          </article>
        </section>
      </section>

      <section v-else class="analysis-page">
        <section class="sheet-stage">
          <div class="sheet-toolbar">
            <div>
              <p class="eyebrow">Spreadsheet Preview</p>
              <h3>{{ selectedFile?.display_name ?? 'No workbook selected' }}</h3>
            </div>
            <div class="sheet-controls">
              <label>
                <span>Version</span>
                <select v-model="selectedVersionId" :disabled="versions.length === 0" @change="selectCurrentVersion">
                  <option value="">Version</option>
                  <option v-for="version in versions" :key="version.version_id" :value="version.version_id">
                    {{ version.status }} - {{ shortId(version.version_id) }}
                  </option>
                </select>
              </label>
              <label>
                <span>Sheet</span>
                <select v-model="selectedSheetId" :disabled="sheets.length === 0" @change="selectCurrentSheet">
                  <option value="">Sheet</option>
                  <option v-for="sheet in sheets" :key="sheet.sheet_id" :value="sheet.sheet_id">
                    {{ sheet.sheet_code }} {{ sheet.sheet_name }}
                  </option>
                </select>
              </label>
              <label class="row-jump">
                <span>Row ID</span>
                <div class="inline-control">
                  <input v-model="lookupRowId" placeholder="S001_R25" type="text" @keydown.enter="lookupRow" />
                  <button type="button" :disabled="isLookupLoading" @click="lookupRow">
                    Find
                  </button>
                </div>
              </label>
            </div>
          </div>

          <div class="sheet-stats">
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

          <section v-if="rowLookup" class="evidence-strip">
            <div>
              <p class="eyebrow">Highlighted Evidence</p>
              <h3>{{ rowLookup.mapping.row_id }}</h3>
            </div>
            <p>
              {{ rowLookup.sheet.sheet_name }} · original row
              {{ rowLookup.mapping.original_row_number }}
            </p>
          </section>

          <section class="spreadsheet-card">
            <div class="spreadsheet-header">
              <div>
                <strong>{{ selectedSheet?.sheet_name ?? 'Sheet preview' }}</strong>
                <span>{{ previewRangeLabel }}</span>
              </div>
              <div class="pagination-actions">
                <button
                  type="button"
                  class="secondary-button"
                  :disabled="!canPreviewPrevious"
                  @click="loadPreviewPage((preview?.offset ?? 0) - previewLimit)"
                >
                  Previous
                </button>
                <button
                  type="button"
                  class="secondary-button"
                  :disabled="!canPreviewNext"
                  @click="loadPreviewPage((preview?.offset ?? 0) + previewLimit)"
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
                    @click="lookupVisibleRow(row)"
                  >
                    <td v-for="(cell, cellIndex) in row" :key="`${row[0]}-${cellIndex}`">
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

          <div class="sheet-tabs" aria-label="Workbook sheets">
            <button
              v-for="sheet in sheets"
              :key="sheet.sheet_id"
              type="button"
              :class="{ active: sheet.sheet_id === selectedSheetId }"
              @click="runInteraction(() => selectSheet(sheet))"
            >
              {{ sheet.sheet_name }}
            </button>
          </div>
        </section>

        <aside class="assistant-column">
          <section class="referenced-docs">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">Referenced Documents</p>
                <h3>{{ referencedDocuments.length }} routed</h3>
              </div>
            </div>
            <button
              v-for="document in referencedDocuments"
              :key="`${document.file_id}-${document.version_id}`"
              type="button"
              class="doc-chip"
              @click="openReferencedDocument(document)"
            >
              <strong>{{ selectedDocumentTitle(document) }}</strong>
              <span>{{ confidenceLabel(document.confidence) }} · {{ document.reason }}</span>
            </button>
            <p v-if="referencedDocuments.length === 0" class="empty-copy">
              No routed documents yet.
            </p>
          </section>

          <ChatPanel
            :router-provider="routerProvider || null"
            :router-model="routerModel || null"
            :answer-provider="answerProvider || null"
            :answer-model="answerModel || null"
            @answer-received="handleChatAnswer"
            @route-received="handleChatRoute"
            @select-citation="handleCitationSelected"
          />
        </aside>
      </section>
    </section>
  </main>
</template>
