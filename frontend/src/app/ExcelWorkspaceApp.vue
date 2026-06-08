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
  renameExcelFile,
  uploadExcelFile,
} from '../api/excel-assets-api'
import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  renameChatSession,
  setChatSessionPinned,
} from '../api/chat-api'
import { generateDocumentSummary, getDocumentSummary } from '../api/document-summaries-api'
import { getLlmModelOptions } from '../api/llm-api'
import AppIcon from '../components/AppIcon.vue'
import ChatPanel from '../components/ChatPanel.vue'
import type { ChatAnswer, ChatSession, ExcelCitation, SelectedDocument } from '../types/chat'
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
type FileInsightTab = 'summary' | 'preview' | 'schema'
type ModelStage = 'summary' | 'router' | 'answer'
type RenameDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }
type ConfirmDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }

const previewLimit = 250
const allowedUploadExtensions = ['.xls', '.xlsx', '.xlsm', '.xltx', '.xltm']

const initialActiveView: ActiveView =
  typeof window !== 'undefined' && window.location.hash === '#chat' ? 'chat' : 'files'

const activeView = ref<ActiveView>(initialActiveView)
const activeFileInsightTab = ref<FileInsightTab>('summary')
const isFileInsightFullscreen = ref<boolean>(false)
const chatSessions = ref<ChatSession[]>([])
const activeChatSessionId = ref<string>('')
const chatSessionError = ref<string>('')
const isChatSessionLoading = ref<boolean>(false)
const files = ref<ExcelFile[]>([])
const versions = ref<ExcelFileVersion[]>([])
const sheets = ref<ExcelSheet[]>([])
const preview = ref<SheetPreviewResponse | null>(null)
const rowLookup = ref<RowLookupResponse | null>(null)
const documentSummary = ref<DocumentSummary | null>(null)
const latestAnswer = ref<ChatAnswer | null>(null)
const selectedFileId = ref<string>('')
const selectedVersionId = ref<string>('')
const selectedSheetId = ref<string>('')
const selectedUploadFile = ref<File | null>(null)
const pendingReplaceFile = ref<File | null>(null)
const pendingDeleteFile = ref<ExcelFile | null>(null)
const renameDialog = ref<RenameDialog | null>(null)
const renameDraft = ref<string>('')
const confirmDialog = ref<ConfirmDialog | null>(null)
const dialogError = ref<string>('')
const toastMessage = ref<string>('')
const openFileActionMenuId = ref<string>('')
const openChatSessionActionMenuId = ref<string>('')
const lookupRowId = ref<string>('')
const statusMessage = ref<string>('Ready')
const errorMessage = ref<string>('')
const searchTerm = ref<string>('')
const isBusy = ref<boolean>(false)
const isSummaryLoading = ref<boolean>(false)
const isLookupLoading = ref<boolean>(false)
const fileInput = ref<HTMLInputElement | null>(null)
const availableLlmModels = ref<string[]>([])
const availableLlmProviders = ref<LlmProviderOption[]>([])
const summaryProvider = ref<string>('siliconflow')
const summaryModel = ref<string>('')
const routerProvider = ref<string>('siliconflow')
const routerModel = ref<string>('')
const answerProvider = ref<string>('siliconflow')
const answerModel = ref<string>('')
let toastTimer: number | null = null

const selectedFile = computed(() => {
  return files.value.find((file) => file.file_id === selectedFileId.value) ?? null
})

const selectedSheet = computed(() => {
  return sheets.value.find((sheet) => sheet.sheet_id === selectedSheetId.value) ?? null
})

const selectedVersion = computed(() => {
  return versions.value.find((version) => version.version_id === selectedVersionId.value) ?? null
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

const schemaColumns = computed(() => {
  const headerRow = preview.value?.offset === 0 ? preview.value.rows[0] ?? [] : []
  const sampleRow = preview.value?.rows.find((row, index) => index > 0 && row.some(Boolean)) ?? []
  return previewHeaders.value.map((label, index) => ({
    key: `${label}-${index}`,
    label,
    sourceName: headerRow[index] || label,
    sample: sampleRow[index] || '-',
    type: index === 0 ? 'Row ID' : 'Text',
  }))
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
  return latestAnswer.value?.selected_documents ?? []
})

const visibleSummaryTopics = computed(() => {
  if (documentSummary.value?.key_topics.length) {
    return documentSummary.value.key_topics.map((topic) => (
      topic.startsWith('#') ? topic : `#${topic.replace(/\s+/g, '_')}`
    ))
  }
  return ['#financial_report', '#q3_performance', '#revenue_growth']
})

const activeChatSession = computed(() => {
  return (
    chatSessions.value.find((session) => session.session_id === activeChatSessionId.value) ??
    null
  )
})


onMounted(() => {
  void initializeWorkspace()
})

async function initializeWorkspace(): Promise<void> {
  await loadLlmModelOptions()
  await loadChatSessions()
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

function setActiveView(view: ActiveView): void {
  closeActionMenus()
  if (view !== 'files') {
    isFileInsightFullscreen.value = false
  }
  activeView.value = view
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', view === 'chat' ? '#chat' : '#files')
  }
}

function setFileInsightTab(tab: FileInsightTab): void {
  closeActionMenus()
  activeFileInsightTab.value = tab
}

function toggleFileInsightFullscreen(): void {
  isFileInsightFullscreen.value = !isFileInsightFullscreen.value
  showToast(isFileInsightFullscreen.value ? 'Expanded detail view.' : 'Restored split view.')
}

function toggleFileActionMenu(fileId: string): void {
  openChatSessionActionMenuId.value = ''
  openFileActionMenuId.value = openFileActionMenuId.value === fileId ? '' : fileId
}

function toggleChatSessionActionMenu(sessionId: string): void {
  openFileActionMenuId.value = ''
  openChatSessionActionMenuId.value =
    openChatSessionActionMenuId.value === sessionId ? '' : sessionId
}

function closeActionMenus(): void {
  openFileActionMenuId.value = ''
  openChatSessionActionMenuId.value = ''
}

async function loadChatSessions(preferredSessionId: string | null = null): Promise<void> {
  chatSessionError.value = ''
  isChatSessionLoading.value = true
  try {
    const sessions = await listChatSessions()
    chatSessions.value = sortChatSessions(sessions)
    const nextActiveSessionId = preferredSessionId || activeChatSessionId.value
    const activeStillExists = chatSessions.value.some(
      (session) => session.session_id === nextActiveSessionId,
    )
    if (nextActiveSessionId && activeStillExists) {
      activeChatSessionId.value = nextActiveSessionId
      return
    }
    activeChatSessionId.value = chatSessions.value[0]?.session_id ?? ''
  } catch (error: unknown) {
    chatSessionError.value = toErrorMessage(error)
  } finally {
    isChatSessionLoading.value = false
  }
}

async function startNewChatSession(): Promise<void> {
  closeActionMenus()
  chatSessionError.value = ''
  isChatSessionLoading.value = true
  try {
    const session = await createChatSession()
    upsertChatSession(session)
    activeChatSessionId.value = session.session_id
    latestAnswer.value = null
    setActiveView('chat')
  } catch (error: unknown) {
    chatSessionError.value = toErrorMessage(error)
  } finally {
    isChatSessionLoading.value = false
  }
}

function selectChatSession(session: ChatSession): void {
  closeActionMenus()
  activeChatSessionId.value = session.session_id
  latestAnswer.value = null
  setActiveView('chat')
}

async function renameChatSessionPrompt(session: ChatSession): Promise<void> {
  closeActionMenus()
  dialogError.value = ''
  renameDialog.value = { kind: 'session', session }
  renameDraft.value = session.title
}

async function toggleChatSessionPin(session: ChatSession): Promise<void> {
  closeActionMenus()
  await updateChatSession(() => setChatSessionPinned(session.session_id, !session.pinned_at))
}

async function removeChatSession(session: ChatSession): Promise<void> {
  closeActionMenus()
  dialogError.value = ''
  confirmDialog.value = { kind: 'session', session }
}

async function confirmDeleteChatSession(session: ChatSession): Promise<void> {
  chatSessionError.value = ''
  isChatSessionLoading.value = true
  try {
    await deleteChatSession(session.session_id)
    confirmDialog.value = null
    showToast('Chat session deleted.')
    chatSessions.value = chatSessions.value.filter(
      (item) => item.session_id !== session.session_id,
    )
    if (activeChatSessionId.value === session.session_id) {
      activeChatSessionId.value = chatSessions.value[0]?.session_id ?? ''
      latestAnswer.value = null
    }
  } catch (error: unknown) {
    chatSessionError.value = toErrorMessage(error)
  } finally {
    isChatSessionLoading.value = false
  }
}

function handleChatSessionCreated(session: ChatSession): void {
  upsertChatSession(session)
  activeChatSessionId.value = session.session_id
}

async function handleChatSessionTitleSuggested(sessionId: string, title: string): Promise<void> {
  const session = chatSessions.value.find((item) => item.session_id === sessionId)
  if (!session || session.title !== 'New chat') {
    return
  }
  await updateChatSession(() => renameChatSession(sessionId, title))
}

async function updateChatSession(action: () => Promise<ChatSession>): Promise<void> {
  chatSessionError.value = ''
  isChatSessionLoading.value = true
  try {
    const session = await action()
    upsertChatSession(session)
  } catch (error: unknown) {
    chatSessionError.value = toErrorMessage(error)
  } finally {
    isChatSessionLoading.value = false
  }
}

function upsertChatSession(session: ChatSession): void {
  const sessions = chatSessions.value.filter((item) => item.session_id !== session.session_id)
  chatSessions.value = sortChatSessions([session, ...sessions])
}

function sortChatSessions(sessions: ChatSession[]): ChatSession[] {
  return [...sessions].sort((left, right) => {
    if (left.pinned_at && !right.pinned_at) {
      return -1
    }
    if (!left.pinned_at && right.pinned_at) {
      return 1
    }
    const leftDate = left.pinned_at || left.updated_at
    const rightDate = right.pinned_at || right.updated_at
    return rightDate.localeCompare(leftDate)
  })
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
  closeActionMenus()
  errorMessage.value = ''
  isBusy.value = true
  try {
    await selectFile(file)
    if (view) {
      setActiveView(view)
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
  closeActionMenus()
  confirmDialog.value = { kind: 'file', file }
  pendingDeleteFile.value = null
  dialogError.value = ''
  errorMessage.value = ''
}

function exportPreviewCsv(): void {
  if (!preview.value || preview.value.rows.length === 0) {
    errorMessage.value = 'No preview rows are available to download.'
    return
  }
  const csvText = preview.value.rows
    .map((row) => row.map((cell) => csvEscape(cell)).join(','))
    .join('\n')
  const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  const objectUrl = URL.createObjectURL(blob)
  link.href = objectUrl
  link.download = `${selectedFile.value?.display_name ?? 'excel-preview'}-${selectedSheet.value?.sheet_code ?? 'sheet'}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
  showToast('Preview downloaded.')
}

async function renameFilePrompt(file: ExcelFile): Promise<void> {
  closeActionMenus()
  dialogError.value = ''
  renameDialog.value = { kind: 'file', file }
  renameDraft.value = file.display_name
}

function cancelDialog(): void {
  renameDialog.value = null
  confirmDialog.value = null
  dialogError.value = ''
  renameDraft.value = ''
}

async function submitRenameDialog(): Promise<void> {
  const dialog = renameDialog.value
  if (!dialog) {
    return
  }

  const trimmedValue = renameDraft.value.trim()
  if (!trimmedValue) {
    dialogError.value =
      dialog.kind === 'file' ? 'Workbook name cannot be empty.' : 'Session title cannot be empty.'
    return
  }

  dialogError.value = ''
  try {
    if (dialog.kind === 'file') {
      errorMessage.value = ''
      isBusy.value = true
      const renamedFile = await renameExcelFile(dialog.file.file_id, trimmedValue)
      files.value = files.value.map((item) => (
        item.file_id === renamedFile.file_id ? renamedFile : item
      ))
      statusMessage.value = `${renamedFile.display_name} renamed`
      showToast('Workbook renamed.')
    } else {
      await updateChatSession(() => renameChatSession(dialog.session.session_id, trimmedValue))
      showToast('Chat session renamed.')
    }
    cancelDialog()
  } catch (error: unknown) {
    dialogError.value = toErrorMessage(error)
  } finally {
    isBusy.value = false
  }
}

async function confirmDeleteFile(): Promise<void> {
  const file =
    confirmDialog.value?.kind === 'file' ? confirmDialog.value.file : pendingDeleteFile.value
  if (!file) {
    return
  }

  errorMessage.value = ''
  isBusy.value = true
  try {
    const result = await deleteExcelFile(file.file_id, true)
    pendingDeleteFile.value = null
    confirmDialog.value = null
    if (selectedFileId.value === file.file_id) {
      clearSelection()
    }
    files.value = await listExcelFiles()
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0])
    }
    statusMessage.value =
      `${result.display_name} deleted. Removed ${result.deleted_versions} version(s), ${result.deleted_sheets} sheet(s), ${result.deleted_artifacts} artifact(s), ${result.deleted_summaries} summary record(s), and ${result.deleted_chat_session_documents} chat attachment(s).`
    showToast('Workbook deleted.')
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingDeleteFile.value = file
      confirmDialog.value = { kind: 'file', file }
      statusMessage.value = `Confirm deletion for ${file.display_name}.`
      return
    }
    dialogError.value = toErrorMessage(error)
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
  setActiveView('chat')
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
  void loadChatSessions(answer.session_id)
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

function fileIcon(file: ExcelFile): string {
  const name = file.display_name.toLowerCase()
  if (name.endsWith('.csv') || name.includes('analysis')) {
    return 'analytics'
  }
  if (name.includes('warehouse') || name.includes('inventory')) {
    return 'description'
  }
  if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.xlsm')) {
    return 'table_chart'
  }
  return 'description'
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

function ensureStageModel(stage: ModelStage): void {
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

function csvEscape(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

function showToast(message: string): void {
  toastMessage.value = message
  if (toastTimer !== null) {
    window.clearTimeout(toastTimer)
  }
  toastTimer = window.setTimeout(() => {
    toastMessage.value = ''
    toastTimer = null
  }, 2400)
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected error.'
}
</script>

<template>
  <main class="excelai-app" :class="{ 'chat-mode': activeView === 'chat' }">
    <aside class="app-sidebar">
      <div class="brand-block">
        <h1>ExcelAI</h1>
        <p>Researcher Pro</p>
      </div>

      <button type="button" class="sidebar-upload-button" :disabled="isBusy" @click="openUploadDialog">
        <AppIcon name="add" />
        <strong>Upload New</strong>
      </button>

      <nav class="primary-nav" aria-label="Primary">
        <button type="button" class="nav-item muted-nav">
          <span class="nav-glyph"><AppIcon name="dashboard" /></span>
          <span>Dashboard</span>
        </button>
        <button
          type="button"
          class="nav-item"
          :class="{ active: activeView === 'files' }"
          @click="setActiveView('files')"
        >
          <span class="nav-glyph"><AppIcon name="folder_open" /></span>
          <span>Files</span>
        </button>
        <button type="button" class="nav-item muted-nav">
          <span class="nav-glyph"><AppIcon name="query_stats" /></span>
          <span>Analytics</span>
        </button>
        <button type="button" class="nav-item muted-nav">
          <span class="nav-glyph"><AppIcon name="auto_awesome" /></span>
          <span>Knowledge Base</span>
        </button>
        <button type="button" class="nav-item muted-nav">
          <span class="nav-glyph"><AppIcon name="settings" /></span>
          <span>Settings</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button type="button" class="nav-item muted-nav support-link">
          <span class="nav-glyph"><AppIcon name="help" /></span>
          <span>Support</span>
        </button>
        <div class="user-mini">
          <div class="avatar">A</div>
          <div>
            <strong>Alex Rivera</strong>
            <span>alex.r@excelai.com</span>
          </div>
          <button type="button" class="logout-button" aria-label="Logout">
            <AppIcon name="logout" />
          </button>
        </div>
      </div>
    </aside>

    <section class="app-main">
      <header class="topbar" :class="{ 'file-topbar': activeView === 'files' }">
        <template v-if="activeView === 'files'">
          <label class="search-field file-search-field">
            <span class="search-icon"><AppIcon name="search" /></span>
            <input v-model="searchTerm" type="search" placeholder="Search knowledge base..." />
          </label>
          <div class="file-topbar-meta">
            <strong>Knowledge Interface</strong>
            <span class="topbar-divider"></span>
            <button type="button" class="topbar-icon-button" aria-label="Notifications">
              <AppIcon name="notifications" />
            </button>
            <button type="button" class="topbar-icon-button" aria-label="History">
              <AppIcon name="history" />
            </button>
            <div class="topbar-avatar">A</div>
          </div>
        </template>
        <template v-else>
          <div>
          <p class="eyebrow">Conversation</p>
          <h2>Excel Analysis</h2>
          </div>
          <div class="topbar-actions">
            <label class="search-field">
              <span class="search-icon"><AppIcon name="search" /></span>
              <input v-model="searchTerm" type="search" placeholder="Search workbooks..." />
            </label>
            <button
              type="button"
              class="view-switch"
              @click="setActiveView('files')"
            >
              Manage Files
            </button>
          </div>
        </template>
      </header>

      <div v-if="errorMessage || (activeView === 'chat' && statusMessage)" class="notice-row">
        <p v-if="activeView === 'chat' && statusMessage" class="status-note">{{ statusMessage }}</p>
        <p v-if="errorMessage" class="error-note">{{ errorMessage }}</p>
      </div>

      <section v-if="activeView === 'files'" class="file-page">
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".xls,.xlsx,.xlsm,.xltx,.xltm"
          @change="handleUploadFileChange"
        />

        <div class="file-management-shell">
          <section class="file-sources-pane">
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

        <section class="file-list-panel">
          <div class="panel-heading">
            <div>
              <h3>Knowledge Sources</h3>
            </div>
            <span class="files-found-label">{{ filteredFiles.length }} Files Found</span>
          </div>

          <div class="file-card-list">
            <article
              v-for="file in filteredFiles"
              :key="file.file_id"
              role="button"
              tabindex="0"
              class="file-library-card"
              :class="{ selected: file.file_id === selectedFileId }"
              @click="chooseFile(file)"
              @keydown.enter.prevent="chooseFile(file)"
              @keydown.space.prevent="chooseFile(file)"
            >
              <span class="file-badge large"><AppIcon :name="fileIcon(file)" /></span>
              <span class="file-card-main">
                <strong>{{ file.display_name }}</strong>
                <span class="file-meta-line">
                  {{ fileTypeLabel(file) }} - Modified {{ formatDate(file.updated_at) }}
                </span>
              </span>
              <span class="file-card-actions" @click.stop>
                <button
                  type="button"
                  class="menu-trigger"
                  :aria-expanded="openFileActionMenuId === file.file_id"
                  aria-label="File actions"
                  @click="toggleFileActionMenu(file.file_id)"
                >
                  <AppIcon name="more_vert" />
                </button>
              </span>
              <span
                v-if="openFileActionMenuId === file.file_id"
                class="item-action-menu file-card-menu"
                @click.stop
              >
                <button type="button" @click="chooseFile(file)">Open</button>
                <button type="button" @click="renameFilePrompt(file)">Rename</button>
                <button type="button" @click="chooseFile(file, 'chat')">Analyze</button>
                <button type="button" class="danger-text" @click="requestDeleteFile(file)">Delete</button>
              </span>
            </article>

            <div v-if="filteredFiles.length === 0" class="file-empty-panel">
              No matching workbooks.
            </div>
          </div>

          <div class="file-pagination">
            <button type="button" class="pagination-link">
              <AppIcon name="chevron_left" />
              Previous
            </button>
            <div class="pagination-pages">
              <span class="active">1</span>
              <span>2</span>
              <span>3</span>
            </div>
            <button type="button" class="pagination-link">
              Next
              <AppIcon name="chevron_right" />
            </button>
          </div>
        </section>

          </section>

          <section class="file-insight-pane" :class="{ fullscreen: isFileInsightFullscreen }">
            <div class="file-insight-tabs">
              <button
                type="button"
                :class="{ active: activeFileInsightTab === 'summary' }"
                @click="setFileInsightTab('summary')"
              >
                Summary
              </button>
              <button
                type="button"
                :class="{ active: activeFileInsightTab === 'preview' }"
                @click="setFileInsightTab('preview')"
              >
                Data Preview
              </button>
              <button
                type="button"
                :class="{ active: activeFileInsightTab === 'schema' }"
                @click="setFileInsightTab('schema')"
              >
                Schema
              </button>
              <div class="file-insight-tools">
                <button
                  type="button"
                  class="icon-only-button"
                  aria-label="Download preview"
                  :disabled="!preview"
                  @click="exportPreviewCsv"
                >
                  <AppIcon name="download" />
                </button>
                <button
                  type="button"
                  class="icon-only-button"
                  aria-label="Fullscreen"
                  @click="toggleFileInsightFullscreen"
                >
                  <AppIcon :name="isFileInsightFullscreen ? 'fullscreen_exit' : 'fullscreen'" />
                </button>
              </div>
            </div>
            <div class="file-insight-scroll">
              <section v-if="activeFileInsightTab === 'summary'" class="file-summary-stack">
                <article v-if="availableLlmProviders.length > 0" class="model-config-card">
                  <div class="config-heading">
                    <div>
                      <span class="config-icon"><AppIcon name="tune" /></span>
                      <h3>Model Settings</h3>
                    </div>
                  </div>
                  <div class="model-config-grid">
                    <div class="model-setting-row">
                      <span>Summary Model</span>
                      <select v-model="summaryProvider" @change="ensureStageModel('summary')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`summary-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="summaryModel">
                        <option
                          v-for="model in modelsForProvider(summaryProvider)"
                          :key="`summary-model-${model}`"
                          :value="model"
                        >
                          {{ model }}
                        </option>
                      </select>
                    </div>
                    <div class="model-setting-row">
                      <span>Router Model</span>
                      <select v-model="routerProvider" @change="ensureStageModel('router')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`router-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="routerModel">
                        <option
                          v-for="model in modelsForProvider(routerProvider)"
                          :key="`router-model-${model}`"
                          :value="model"
                        >
                          {{ model }}
                        </option>
                      </select>
                    </div>
                    <div class="model-setting-row">
                      <span>Chat Model</span>
                      <select v-model="answerProvider" @change="ensureStageModel('answer')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`answer-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="answerModel">
                        <option
                          v-for="model in modelsForProvider(answerProvider)"
                          :key="`answer-model-${model}`"
                          :value="model"
                        >
                          {{ model }}
                        </option>
                      </select>
                    </div>
                  </div>
                </article>

                <article class="document-summary-card">
                  <div class="summary-card-head">
                    <div>
                      <span class="summary-icon"><AppIcon name="auto_awesome" /></span>
                      <h3>AI Executive Summary</h3>
                    </div>
                    <div class="summary-head-actions">
                      <button
                        type="button"
                        class="secondary-button"
                        :disabled="isSummaryLoading || !selectedVersionId"
                        @click="generateSummaryForSelectedVersion"
                      >
                        <AppIcon name="refresh" />
                        {{ isSummaryLoading ? 'Generating...' : 'Regenerate' }}
                      </button>
                      <button
                        type="button"
                        class="summary-edit-button"
                        aria-label="Edit summary"
                      >
                        <AppIcon name="edit" />
                      </button>
                    </div>
                  </div>

                  <div v-if="documentSummary" class="summary-content">
                    <p class="summary-text">{{ documentSummary.summary_text }}</p>
                  </div>
                  <div v-else class="insight-empty-state">
                    <div class="insight-icon"><AppIcon name="auto_awesome" /></div>
                    <h4>No summary generated</h4>
                    <p>Select a file and click generate to see AI insights.</p>
                    <button
                      type="button"
                      class="primary-action"
                      :disabled="isSummaryLoading || !selectedVersionId"
                      @click="generateSummaryForSelectedVersion"
                    >
                      <AppIcon name="bolt" />
                      {{ isSummaryLoading ? 'Generating...' : 'Generate Summary' }}
                    </button>
                  </div>

                  <div class="topic-toolbar">
                    <span>Keywords & Tags</span>
                    <button type="button">+ Add Tag</button>
                  </div>
                  <div class="topic-list">
                    <span v-for="topic in visibleSummaryTopics" :key="topic">
                      {{ topic }}
                      <AppIcon name="close" />
                    </span>
                  </div>
                </article>
              </section>

              <section v-else-if="activeFileInsightTab === 'preview'" class="file-preview-panel">
                <div class="file-preview-controls">
                  <label>
                    <span>Version</span>
                    <select
                      v-model="selectedVersionId"
                      :disabled="versions.length === 0"
                      @change="selectCurrentVersion"
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
                      v-model="selectedSheetId"
                      :disabled="sheets.length === 0"
                      @change="selectCurrentSheet"
                    >
                      <option value="">Sheet</option>
                      <option
                        v-for="sheet in sheets"
                        :key="sheet.sheet_id"
                        :value="sheet.sheet_id"
                      >
                        {{ sheet.sheet_code }} {{ sheet.sheet_name }}
                      </option>
                    </select>
                  </label>
                  <label class="row-jump">
                    <span>Row ID</span>
                    <div class="inline-control">
                      <input
                        v-model="lookupRowId"
                        placeholder="S001_R25"
                        type="text"
                        @keydown.enter="lookupRow"
                      />
                      <button type="button" :disabled="isLookupLoading" @click="lookupRow">
                        Find
                      </button>
                    </div>
                  </label>
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

                <div class="sheet-tabs compact" aria-label="Workbook sheets">
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

              <section v-else class="file-schema-panel">
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
                      @click="runInteraction(() => selectSheet(sheet))"
                    >
                      <strong>{{ sheet.sheet_code }} {{ sheet.sheet_name }}</strong>
                      <span>{{ sheet.row_count }} rows / {{ sheet.column_count }} columns</span>
                    </button>
                    <div v-if="sheets.length === 0" class="file-empty-panel">
                      No sheets available.
                    </div>
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
                    <div v-if="schemaColumns.length === 0" class="file-empty-panel">
                      Select a sheet to inspect columns.
                    </div>
                  </div>
                </article>
              </section>
            </div>
          </section>
        </div>
        <button
          type="button"
          class="file-chat-fab"
          aria-label="Open chat"
          @click="setActiveView('chat')"
        >
          <AppIcon name="chat_bubble" />
        </button>
      </section>

      <section v-else class="analysis-page">
        <aside class="chat-session-rail">
          <div class="chat-rail-brand">
            <div class="rail-logo">EA</div>
            <div>
              <h3>ExcelAI</h3>
              <p>Data Analyst Pro</p>
            </div>
          </div>

          <button
            type="button"
            class="new-chat-button"
            :disabled="isChatSessionLoading"
            @click="startNewChatSession"
          >
            <span>+</span>
            <strong>New Chat</strong>
          </button>

          <div class="session-section-head">
            <span>Recent</span>
            <button type="button" :disabled="isChatSessionLoading" @click="loadChatSessions()">
              Refresh
            </button>
          </div>

          <div class="chat-session-list">
            <article
              v-for="session in chatSessions"
              :key="session.session_id"
              role="button"
              tabindex="0"
              class="chat-session-item"
              :class="{
                active: session.session_id === activeChatSessionId,
                pinned: Boolean(session.pinned_at),
              }"
              @click="selectChatSession(session)"
              @keydown.enter.prevent="selectChatSession(session)"
              @keydown.space.prevent="selectChatSession(session)"
            >
              <span class="session-glyph">{{ session.pinned_at ? 'P' : 'C' }}</span>
              <span class="session-copy">
                <strong>{{ session.title }}</strong>
                <small>{{ formatDate(session.updated_at) }}</small>
              </span>
              <span class="session-actions" @click.stop>
                <button
                  type="button"
                  class="menu-trigger compact"
                  :aria-expanded="openChatSessionActionMenuId === session.session_id"
                  aria-label="Session actions"
                  @click="toggleChatSessionActionMenu(session.session_id)"
                >
                  ...
                </button>
              </span>
              <span
                v-if="openChatSessionActionMenuId === session.session_id"
                class="item-action-menu session-action-menu"
                @click.stop
              >
                <button type="button" @click="selectChatSession(session)">Open</button>
                <button type="button" @click="toggleChatSessionPin(session)">
                  {{ session.pinned_at ? 'Unpin' : 'Pin' }}
                </button>
                <button type="button" @click="renameChatSessionPrompt(session)">Rename</button>
                <button type="button" class="danger-text" @click="removeChatSession(session)">Delete</button>
              </span>
            </article>

            <div v-if="chatSessions.length === 0" class="session-empty-state">
              No chat sessions yet.
            </div>
          </div>

          <p v-if="chatSessionError" class="error-note session-error">{{ chatSessionError }}</p>

          <div class="rail-system-links">
            <button type="button" @click="setActiveView('files')">Files</button>
            <button type="button" disabled>History</button>
            <button type="button" disabled>Settings</button>
          </div>
        </aside>

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
              {{ rowLookup.sheet.sheet_name }} / original row
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
              <span>{{ confidenceLabel(document.confidence) }} / {{ document.reason }}</span>
            </button>
            <p v-if="referencedDocuments.length === 0" class="empty-copy">
              No routed documents yet.
            </p>
          </section>

          <ChatPanel
            :session-id="activeChatSessionId"
            :session-title="activeChatSession?.title ?? ''"
            :router-provider="routerProvider || null"
            :router-model="routerModel || null"
            :answer-provider="answerProvider || null"
            :answer-model="answerModel || null"
            @answer-received="handleChatAnswer"
            @select-citation="handleCitationSelected"
            @session-created="handleChatSessionCreated"
            @session-title-suggested="handleChatSessionTitleSuggested"
          />
        </aside>
      </section>
    </section>

    <div v-if="toastMessage" class="app-toast" role="status">
      {{ toastMessage }}
    </div>

    <section
      v-if="renameDialog"
      class="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rename-dialog-title"
      @keydown.esc="cancelDialog"
    >
      <form class="app-dialog" @submit.prevent="submitRenameDialog">
        <div class="dialog-heading">
          <div>
            <p class="eyebrow">{{ renameDialog.kind === 'file' ? 'Workbook' : 'Chat Session' }}</p>
            <h3 id="rename-dialog-title">Rename</h3>
          </div>
          <button type="button" class="dialog-icon-button" aria-label="Close" @click="cancelDialog">
            <AppIcon name="close" />
          </button>
        </div>
        <label class="dialog-field">
          <span>Name</span>
          <input v-model="renameDraft" type="text" autocomplete="off" />
        </label>
        <p v-if="dialogError" class="dialog-error">{{ dialogError }}</p>
        <div class="dialog-actions">
          <button type="button" class="dialog-secondary" @click="cancelDialog">Cancel</button>
          <button type="submit" class="dialog-primary" :disabled="isBusy || isChatSessionLoading">
            Save
          </button>
        </div>
      </form>
    </section>

    <section
      v-if="confirmDialog"
      class="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      @keydown.esc="cancelDialog"
    >
      <div class="app-dialog">
        <div class="dialog-heading">
          <div>
            <p class="eyebrow">{{ confirmDialog.kind === 'file' ? 'Workbook' : 'Chat Session' }}</p>
            <h3 id="confirm-dialog-title">Delete</h3>
          </div>
          <button type="button" class="dialog-icon-button" aria-label="Close" @click="cancelDialog">
            <AppIcon name="close" />
          </button>
        </div>
        <p class="dialog-copy">
          {{
            confirmDialog.kind === 'file'
              ? `Delete "${confirmDialog.file.display_name}" and all related versions, artifacts, summaries, and chat attachments?`
              : `Delete "${confirmDialog.session.title}"?`
          }}
        </p>
        <p v-if="dialogError" class="dialog-error">{{ dialogError }}</p>
        <div class="dialog-actions">
          <button type="button" class="dialog-secondary" @click="cancelDialog">Cancel</button>
          <button
            type="button"
            class="dialog-danger"
            :disabled="isBusy || isChatSessionLoading"
            @click="
              confirmDialog.kind === 'file'
                ? confirmDeleteFile()
                : confirmDeleteChatSession(confirmDialog.session)
            "
          >
            Delete
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
