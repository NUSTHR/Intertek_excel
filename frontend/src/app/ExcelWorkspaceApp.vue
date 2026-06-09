<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

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
type UploadDialog =
  | { kind: 'new'; file: File }
  | { kind: 'replace'; file: File }
interface SelectedCell {
  rowKey: string
  rowNumber: number
  columnIndex: number
  address: string
  value: string
}

const previewLimit = 250
const allowedUploadExtensions = ['.xls', '.xlsx', '.xlsm', '.xltx', '.xltm', '.csv']
const pinnedFileStorageKey = 'excelai-pinned-file-ids'
const defaultRouterProvider = 'deepseek'
const defaultRouterModel = 'deepseek-v4-flash'
const maxUploadBytes = 50 * 1024 * 1024
const minChatColumnWidth = 360
const maxChatColumnWidth = 560
const defaultExcelCellWidth = 120
const defaultExcelRowHeight = 42
const minExcelCellWidth = 92
const maxExcelCellWidth = 260
const minExcelRowHeight = 30
const maxExcelRowHeight = 86

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
const uploadDialog = ref<UploadDialog | null>(null)
const dialogError = ref<string>('')
const transientToastMessage = ref<string>('')
const openFileActionMenuId = ref<string>('')
const openChatSessionActionMenuId = ref<string>('')
const lookupRowId = ref<string>('')
const operationNotice = ref<string>('')
const errorMessage = ref<string>('')
const searchTerm = ref<string>('')
const isWorkspaceBusy = ref<boolean>(false)
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
const pinnedFileIds = ref<string[]>(loadPinnedFileIds())
const selectedCell = ref<SelectedCell | null>(null)
const excelColumnWidths = ref<Record<string, number>>({})
const excelRowHeights = ref<Record<string, number>>({})
const chatColumnWidth = ref<number>(420)
const isChatResizing = ref<boolean>(false)
const isUploadDragging = ref<boolean>(false)
const isExcelColumnResizing = ref<boolean>(false)
const isExcelRowResizing = ref<boolean>(false)
let transientToastTimer: number | null = null
let operationNoticeTimer: number | null = null
let excelResizeStartX = 0
let excelResizeStartY = 0
let excelResizeStartWidth = 0
let excelResizeStartHeight = 0
let excelResizeTargetColumnKey = ''
let excelResizeTargetRowKey = ''

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
  const visibleFiles = !query
    ? files.value
    : files.value.filter((file) => file.display_name.toLowerCase().includes(query))
  return sortFilesForDisplay(visibleFiles)
})

const previewHeaders = computed(() => {
  const widestRow = preview.value?.rows.reduce((width, row) => Math.max(width, row.length), 0) ?? 0
  return Array.from({ length: widestRow }, (_value, index) =>
    index === 0 ? '_id' : columnLabel(index),
  )
})

const excelDataColumnCount = computed(() => {
  const widestDataRow = preview.value?.rows.reduce(
    (width, row) => Math.max(width, Math.max(0, row.length - 1)),
    0,
  ) ?? 0
  return Math.max(6, widestDataRow, Math.max(0, previewHeaders.value.length - 1))
})

const excelColumnLabels = computed(() => {
  return Array.from({ length: excelDataColumnCount.value }, (_value, index) =>
    columnLabel(index + 1),
  )
})

const excelDisplayRows = computed(() => {
  return preview.value?.rows ?? []
})

const excelFillerRowCount = computed(() => {
  return Math.max(0, 25 - excelDisplayRows.value.length)
})

const selectedFileDisplayName = computed(() => {
  return selectedFile.value?.display_name ?? 'No workbook selected'
})

const workbookStatusLabel = computed(() => {
  if (!selectedFile.value) {
    return 'No active workbook'
  }
  const sheetLabel = selectedSheet.value?.sheet_name ?? 'No sheet selected'
  return `${sheetLabel} / ${previewRangeLabel.value}`
})

const selectedCellAddress = computed(() => selectedCell.value?.address ?? 'C5')

const selectedCellValue = computed(() => selectedCell.value?.value || '-')

const chatWorkspaceStyle = computed(() => ({
  '--chat-column-width': `${chatColumnWidth.value}px`,
}))

const excelGridStyle = computed(() => ({
  '--excel-column-count': excelDataColumnCount.value,
  '--excel-grid-columns': excelGridTemplateColumns.value,
  '--excel-row-height': `${defaultExcelRowHeight}px`,
}))

const excelGridTemplateColumns = computed(() => {
  const dataColumns = Array.from({ length: excelDataColumnCount.value }, (_value, index) => {
    return `${getExcelColumnWidth(index + 1)}px`
  })
  return ['48px', ...dataColumns].join(' ')
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

const documentTitleMap = computed<Record<string, string>>(() => {
  return Object.fromEntries(files.value.map((file) => [file.file_id, file.display_name]))
})

const activeDocumentForChat = computed<SelectedDocument | null>(() => {
  const file = selectedFile.value
  if (!file) {
    return null
  }
  const versionId = selectedVersionId.value || file.active_version_id
  if (!versionId) {
    return null
  }
  return {
    file_id: file.file_id,
    version_id: versionId,
    reason: 'Current workbook',
    confidence: null,
  }
})

const visibleSummaryTopics = computed(() => {
  if (documentSummary.value?.key_topics.length) {
    return documentSummary.value.key_topics.map((topic) => (
      topic.startsWith('#') ? topic : `#${topic.replace(/\s+/g, '_')}`
    ))
  }
  return []
})

const activeChatSession = computed(() => {
  return (
    chatSessions.value.find((session) => session.session_id === activeChatSessionId.value) ??
    null
  )
})


onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', syncActiveViewFromLocation)
  }
  void initializeWorkspace()
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('hashchange', syncActiveViewFromLocation)
  }
  clearOperationNotice()
  clearTransientToast()
  stopChatResize()
  stopExcelColumnResize()
  stopExcelRowResize()
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
  routerProvider.value = preferredRouterProvider(defaults.router_provider)
  routerModel.value = preferredRouterModel(defaults.router_model)
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

function syncActiveViewFromLocation(): void {
  if (typeof window === 'undefined') {
    return
  }
  const nextView: ActiveView = window.location.hash === '#chat' ? 'chat' : 'files'
  if (activeView.value === nextView) {
    return
  }
  closeActionMenus()
  if (nextView !== 'files') {
    isFileInsightFullscreen.value = false
  }
  activeView.value = nextView
}

function setFileInsightTab(tab: FileInsightTab): void {
  closeActionMenus()
  activeFileInsightTab.value = tab
}

function toggleFileInsightFullscreen(): void {
  isFileInsightFullscreen.value = !isFileInsightFullscreen.value
  showTransientToast(isFileInsightFullscreen.value ? 'Expanded detail view.' : 'Restored split view.')
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
    clearSelection()
    selectedCell.value = null
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
    showTransientToast('Chat session deleted.')
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

function sortFilesForDisplay(items: ExcelFile[]): ExcelFile[] {
  return [...items].sort((left, right) => {
    const leftPinned = isFilePinned(left.file_id)
    const rightPinned = isFilePinned(right.file_id)
    if (leftPinned && !rightPinned) {
      return -1
    }
    if (!leftPinned && rightPinned) {
      return 1
    }
    return right.updated_at.localeCompare(left.updated_at)
  })
}

function isFilePinned(fileId: string): boolean {
  return pinnedFileIds.value.includes(fileId)
}

function toggleFilePin(file: ExcelFile): void {
  closeActionMenus()
  const nextIds = isFilePinned(file.file_id)
    ? pinnedFileIds.value.filter((fileId) => fileId !== file.file_id)
    : [file.file_id, ...pinnedFileIds.value]
  pinnedFileIds.value = nextIds
  savePinnedFileIds(nextIds)
  showTransientToast(isFilePinned(file.file_id) ? 'Workbook pinned.' : 'Workbook unpinned.')
}

function loadPinnedFileIds(): string[] {
  if (typeof window === 'undefined') {
    return []
  }
  const storedValue = window.localStorage.getItem(pinnedFileStorageKey)
  if (!storedValue) {
    return []
  }
  try {
    const parsedValue = JSON.parse(storedValue)
    return Array.isArray(parsedValue)
      ? parsedValue.filter((item): item is string => typeof item === 'string')
      : []
  } catch {
    return []
  }
}

function savePinnedFileIds(fileIds: string[]): void {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(pinnedFileStorageKey, JSON.stringify(fileIds))
}

async function refreshFiles(): Promise<void> {
  errorMessage.value = ''
  isWorkspaceBusy.value = true
  try {
    files.value = await listExcelFiles()
    const selectedStillExists = files.value.some((file) => file.file_id === selectedFileId.value)
    if (!selectedStillExists) {
      clearSelection()
    }
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0])
    }
    showOperationNotice(
      `${files.value.length} workbook${files.value.length === 1 ? '' : 's'} loaded`,
    )
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isWorkspaceBusy.value = false
  }
}

async function chooseFile(file: ExcelFile, view: ActiveView | null = null): Promise<void> {
  closeActionMenus()
  errorMessage.value = ''
  isWorkspaceBusy.value = true
  try {
    await selectFile(file)
    if (view) {
      setActiveView(view)
    }
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isWorkspaceBusy.value = false
  }
}

async function selectFile(file: ExcelFile): Promise<void> {
  selectedFileId.value = file.file_id
  selectedVersionId.value = ''
  selectedSheetId.value = ''
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  selectedCell.value = null
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
  selectedCell.value = null
  sheets.value = await listExcelSheets(versionId)
  await loadExistingSummary(versionId)
  if (sheets.value[0]) {
    await selectSheet(sheets.value[0])
  }
}

async function selectCurrentVersion(): Promise<void> {
  if (selectedVersionId.value) {
    await runWorkspaceAction(() => selectVersion(selectedVersionId.value))
  }
}

async function selectCurrentSheet(): Promise<void> {
  const sheet = sheets.value.find((item) => item.sheet_id === selectedSheetId.value)
  if (sheet) {
    await runWorkspaceAction(() => selectSheet(sheet))
  }
}

async function selectSheet(sheet: ExcelSheet): Promise<void> {
  selectedSheetId.value = sheet.sheet_id
  rowLookup.value = null
  lookupRowId.value = ''
  selectedCell.value = null
  preview.value = await previewExcelSheet(sheet.sheet_id, 0, previewLimit)
}

async function loadPreviewPage(offset: number): Promise<void> {
  if (!selectedSheetId.value) {
    return
  }
  errorMessage.value = ''
  try {
    const safeOffset = Math.max(0, offset)
    rowLookup.value = null
    selectedCell.value = null
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
    showOperationNotice('Document description generated')
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

function handleUploadDragEnter(): void {
  if (!isWorkspaceBusy.value) {
    isUploadDragging.value = true
  }
}

function handleUploadDragLeave(event: DragEvent): void {
  if (!(event.currentTarget instanceof HTMLElement)) {
    isUploadDragging.value = false
    return
  }
  const relatedTarget = event.relatedTarget
  if (!(relatedTarget instanceof Node) || !event.currentTarget.contains(relatedTarget)) {
    isUploadDragging.value = false
  }
}

function handleUploadDrop(event: DragEvent): void {
  isUploadDragging.value = false
  if (isWorkspaceBusy.value) {
    return
  }
  setUploadFile(event.dataTransfer?.files?.[0] ?? null)
}

function setUploadFile(file: File | null): void {
  pendingReplaceFile.value = null
  uploadDialog.value = null
  if (!file) {
    selectedUploadFile.value = null
    return
  }
  if (!isAllowedUploadFile(file)) {
    selectedUploadFile.value = null
    errorMessage.value = 'Only Excel and CSV files are supported: .xls, .xlsx, .xlsm, .xltx, .xltm, .csv.'
    return
  }
  if (file.size > maxUploadBytes) {
    selectedUploadFile.value = null
    errorMessage.value = 'File is larger than 50MB.'
    return
  }
  errorMessage.value = ''
  selectedUploadFile.value = file
  uploadDialog.value = { kind: 'new', file }
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
  showTransientToast('Preview downloaded.')
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
  uploadDialog.value = null
  dialogError.value = ''
  renameDraft.value = ''
  selectedUploadFile.value = null
  pendingReplaceFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function cancelUploadDialog(): void {
  uploadDialog.value = null
  dialogError.value = ''
  selectedUploadFile.value = null
  pendingReplaceFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

async function confirmUploadDialog(): Promise<void> {
  const dialog = uploadDialog.value
  if (!dialog) {
    return
  }
  await uploadSelectedFile(dialog.kind === 'replace')
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
      isWorkspaceBusy.value = true
      const renamedFile = await renameExcelFile(dialog.file.file_id, trimmedValue)
      files.value = files.value.map((item) => (
        item.file_id === renamedFile.file_id ? renamedFile : item
      ))
      showOperationNotice(`${renamedFile.display_name} renamed`)
      showTransientToast('Workbook renamed.')
    } else {
      await updateChatSession(() => renameChatSession(dialog.session.session_id, trimmedValue))
      showTransientToast('Chat session renamed.')
    }
    cancelDialog()
  } catch (error: unknown) {
    dialogError.value = toErrorMessage(error)
  } finally {
    isWorkspaceBusy.value = false
  }
}

async function confirmDeleteFile(): Promise<void> {
  const file =
    confirmDialog.value?.kind === 'file' ? confirmDialog.value.file : pendingDeleteFile.value
  if (!file) {
    return
  }

  errorMessage.value = ''
  isWorkspaceBusy.value = true
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
    showOperationNotice(
      `${result.display_name} deleted. Removed ${result.deleted_versions} version(s), ${result.deleted_sheets} sheet(s), ${result.deleted_artifacts} artifact(s), ${result.deleted_summaries} summary record(s), and ${result.deleted_chat_session_documents} chat attachment(s).`
    )
    showTransientToast('Workbook deleted.')
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingDeleteFile.value = file
      confirmDialog.value = { kind: 'file', file }
      showOperationNotice(`Confirm deletion for ${file.display_name}.`, 5000)
      return
    }
    dialogError.value = toErrorMessage(error)
  } finally {
    isWorkspaceBusy.value = false
  }
}

async function uploadSelectedFile(replaceExisting = false): Promise<void> {
  const file = replaceExisting ? pendingReplaceFile.value : selectedUploadFile.value
  if (!file) {
    errorMessage.value = 'Choose an Excel workbook first.'
    return
  }

  errorMessage.value = ''
  isWorkspaceBusy.value = true
  try {
    const result = await uploadExcelFile(file, replaceExisting)
    pendingReplaceFile.value = null
    selectedUploadFile.value = null
    uploadDialog.value = null
    dialogError.value = ''
    if (fileInput.value) {
      fileInput.value.value = ''
    }
    showOperationNotice(`${result.file.display_name} uploaded and parsed`)
    files.value = await listExcelFiles()
    const uploadedFile = files.value.find((item) => item.file_id === result.file.file_id)
    if (uploadedFile) {
      await selectFile(uploadedFile)
    }
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingReplaceFile.value = file
      selectedUploadFile.value = null
      uploadDialog.value = { kind: 'replace', file }
      dialogError.value = ''
      return
    }
    if (uploadDialog.value) {
      dialogError.value = toErrorMessage(error)
    } else {
      errorMessage.value = toErrorMessage(error)
    }
  } finally {
    isWorkspaceBusy.value = false
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
    selectedCell.value = null
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
    await runWorkspaceAction(() => selectVersion(document.version_id))
  }
}

async function runWorkspaceAction(action: () => Promise<void>): Promise<void> {
  errorMessage.value = ''
  isWorkspaceBusy.value = true
  try {
    await action()
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  } finally {
    isWorkspaceBusy.value = false
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
  selectedCell.value = null
}

function rowIsHighlighted(row: string[]): boolean {
  return Boolean(rowLookup.value && row[0] === rowLookup.value.mapping.row_id)
}

function selectGridCell(row: string[], rowIndex: number, columnIndex: number): void {
  const rowNumber = (preview.value?.offset ?? 0) + rowIndex + 1
  selectedCell.value = {
    rowKey: row[0] || `${rowNumber}`,
    rowNumber,
    columnIndex,
    address: `${columnLabel(columnIndex)}${rowNumber}`,
    value: getGridCellValue(row, columnIndex),
  }
}

function isGridCellSelected(row: string[], rowIndex: number, columnIndex: number): boolean {
  const cell = selectedCell.value
  if (!cell) {
    return false
  }
  const rowNumber = (preview.value?.offset ?? 0) + rowIndex + 1
  const rowKey = row[0] || `${rowNumber}`
  return cell.rowKey === rowKey && cell.columnIndex === columnIndex
}

function startChatResize(event: PointerEvent): void {
  event.preventDefault()
  isChatResizing.value = true
  window.addEventListener('pointermove', handleChatResize)
  window.addEventListener('pointerup', stopChatResize)
  window.addEventListener('pointercancel', stopChatResize)
}

function handleChatResize(event: PointerEvent): void {
  const viewportWidth = window.innerWidth
  const nextWidth = Math.round(viewportWidth - event.clientX)
  chatColumnWidth.value = clamp(nextWidth, minChatColumnWidth, maxChatColumnWidth)
}

function stopChatResize(): void {
  if (!isChatResizing.value) {
    return
  }
  isChatResizing.value = false
  window.removeEventListener('pointermove', handleChatResize)
  window.removeEventListener('pointerup', stopChatResize)
  window.removeEventListener('pointercancel', stopChatResize)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function excelColumnKey(columnIndex: number): string {
  return `${selectedSheetId.value || 'sheet'}:C${columnIndex}`
}

function excelRowKey(row: string[], rowIndex: number): string {
  const rowNumber = (preview.value?.offset ?? 0) + rowIndex + 1
  return `${selectedSheetId.value || 'sheet'}:${row[0] || `R${rowNumber}`}`
}

function fillerExcelRowKey(fillerIndex: number): string {
  return `${selectedSheetId.value || 'sheet'}:F${fillerRowNumber(fillerIndex)}`
}

function fillerRowNumber(fillerIndex: number): number {
  return (preview.value?.offset ?? 0) + excelDisplayRows.value.length + fillerIndex + 1
}

function getGridCellValue(row: string[], columnIndex: number): string {
  return row[columnIndex] ?? ''
}

function getExcelColumnWidth(columnIndex: number): number {
  return excelColumnWidths.value[excelColumnKey(columnIndex)] ?? defaultExcelCellWidth
}

function getExcelRowHeight(rowKey: string): number {
  return excelRowHeights.value[rowKey] ?? defaultExcelRowHeight
}

function getExcelRowStyle(row: string[], rowIndex: number): Record<string, string> {
  return {
    '--excel-row-height-current': `${getExcelRowHeight(excelRowKey(row, rowIndex))}px`,
  }
}

function getFillerExcelRowStyle(fillerIndex: number): Record<string, string> {
  return {
    '--excel-row-height-current': `${getExcelRowHeight(fillerExcelRowKey(fillerIndex))}px`,
  }
}

function startExcelColumnResize(event: PointerEvent, columnIndex: number): void {
  event.preventDefault()
  event.stopPropagation()
  isExcelColumnResizing.value = true
  excelResizeStartX = event.clientX
  excelResizeTargetColumnKey = excelColumnKey(columnIndex)
  excelResizeStartWidth = getExcelColumnWidth(columnIndex)
  window.addEventListener('pointermove', handleExcelColumnResize)
  window.addEventListener('pointerup', stopExcelColumnResize)
  window.addEventListener('pointercancel', stopExcelColumnResize)
}

function startExcelColumnResizeFromHeader(event: PointerEvent, columnIndex: number): void {
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  if (rect.right - event.clientX > 14) {
    return
  }
  startExcelColumnResize(event, columnIndex)
}

function handleExcelColumnResize(event: PointerEvent): void {
  if (!excelResizeTargetColumnKey) {
    return
  }
  const nextWidth = clamp(
    excelResizeStartWidth + event.clientX - excelResizeStartX,
    minExcelCellWidth,
    maxExcelCellWidth,
  )
  excelColumnWidths.value = {
    ...excelColumnWidths.value,
    [excelResizeTargetColumnKey]: nextWidth,
  }
}

function stopExcelColumnResize(): void {
  if (!isExcelColumnResizing.value) {
    return
  }
  isExcelColumnResizing.value = false
  excelResizeTargetColumnKey = ''
  window.removeEventListener('pointermove', handleExcelColumnResize)
  window.removeEventListener('pointerup', stopExcelColumnResize)
  window.removeEventListener('pointercancel', stopExcelColumnResize)
}

function startExcelRowResize(event: PointerEvent, rowKey: string): void {
  event.preventDefault()
  event.stopPropagation()
  isExcelRowResizing.value = true
  excelResizeStartY = event.clientY
  excelResizeTargetRowKey = rowKey
  excelResizeStartHeight = getExcelRowHeight(rowKey)
  window.addEventListener('pointermove', handleExcelRowResize)
  window.addEventListener('pointerup', stopExcelRowResize)
  window.addEventListener('pointercancel', stopExcelRowResize)
}

function handleExcelRowResize(event: PointerEvent): void {
  if (!excelResizeTargetRowKey) {
    return
  }
  const nextHeight = clamp(
    excelResizeStartHeight + event.clientY - excelResizeStartY,
    minExcelRowHeight,
    maxExcelRowHeight,
  )
  excelRowHeights.value = {
    ...excelRowHeights.value,
    [excelResizeTargetRowKey]: nextHeight,
  }
}

function stopExcelRowResize(): void {
  if (!isExcelRowResizing.value) {
    return
  }
  isExcelRowResizing.value = false
  excelResizeTargetRowKey = ''
  window.removeEventListener('pointermove', handleExcelRowResize)
  window.removeEventListener('pointerup', stopExcelRowResize)
  window.removeEventListener('pointercancel', stopExcelRowResize)
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

function modelsForProvider(provider: string): string[] {
  return availableLlmProviders.value.find((item) => item.provider === provider)?.models ?? []
}

function preferredRouterProvider(fallbackProvider: string): string {
  return availableLlmProviders.value.some((provider) => provider.provider === defaultRouterProvider)
    ? defaultRouterProvider
    : fallbackProvider
}

function preferredRouterModel(fallbackModel: string): string {
  const providerModels = modelsForProvider(routerProvider.value)
  const exactMatch = providerModels.find((model) => model === defaultRouterModel)
  if (exactMatch) {
    return exactMatch
  }
  const semanticMatch = providerModels.find((model) => {
    const normalizedModel = model.toLowerCase()
    return normalizedModel.includes('deepseek') && normalizedModel.includes('flash')
  })
  return semanticMatch ?? fallbackModel
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

function showOperationNotice(message: string, durationMs = 3200): void {
  operationNotice.value = message
  if (operationNoticeTimer !== null) {
    window.clearTimeout(operationNoticeTimer)
  }
  operationNoticeTimer = window.setTimeout(() => {
    operationNotice.value = ''
    operationNoticeTimer = null
  }, durationMs)
}

function clearOperationNotice(): void {
  if (operationNoticeTimer !== null) {
    window.clearTimeout(operationNoticeTimer)
    operationNoticeTimer = null
  }
  operationNotice.value = ''
}

function showTransientToast(message: string): void {
  transientToastMessage.value = message
  if (transientToastTimer !== null) {
    window.clearTimeout(transientToastTimer)
  }
  transientToastTimer = window.setTimeout(() => {
    transientToastMessage.value = ''
    transientToastTimer = null
  }, 2400)
}

function clearTransientToast(): void {
  if (transientToastTimer !== null) {
    window.clearTimeout(transientToastTimer)
    transientToastTimer = null
  }
  transientToastMessage.value = ''
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
        <button
          type="button"
          class="nav-item"
          :class="{ active: activeView === 'chat' }"
          @click="setActiveView('chat')"
        >
          <span class="nav-glyph"><AppIcon name="chat_bubble" /></span>
          <span>Chat</span>
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

      <div v-if="errorMessage || (activeView === 'chat' && operationNotice)" class="notice-row">
        <p v-if="activeView === 'chat' && operationNotice" class="status-note">
          {{ operationNotice }}
        </p>
        <p v-if="errorMessage" class="error-note">{{ errorMessage }}</p>
      </div>

      <section v-if="activeView === 'files'" class="file-page">
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".xls,.xlsx,.xlsm,.xltx,.xltm,.csv"
          @change="handleUploadFileChange"
        />

        <div class="file-management-shell">
          <section class="file-sources-pane">
        <section class="file-list-panel">
          <div class="panel-heading">
            <div>
              <h3>Knowledge Sources</h3>
            </div>
            <span class="files-found-label">{{ filteredFiles.length }} Files Found</span>
          </div>

          <button
            type="button"
            class="knowledge-upload-zone"
            :class="{ dragging: isUploadDragging }"
            :disabled="isWorkspaceBusy"
            @click="openUploadDialog"
            @dragenter.prevent="handleUploadDragEnter"
            @dragover.prevent="handleUploadDragEnter"
            @dragleave.prevent="handleUploadDragLeave"
            @drop.prevent="handleUploadDrop"
          >
            <span class="knowledge-upload-icon">
              <AppIcon name="upload_file" />
            </span>
            <strong>Click or drag files to upload</strong>
            <span>Supports Excel, CSV (Max 50MB)</span>
          </button>

          <div class="file-card-list">
            <article
              v-for="file in filteredFiles"
              :key="file.file_id"
              role="button"
              tabindex="0"
              class="file-library-card"
              :class="{
                selected: file.file_id === selectedFileId,
                pinned: isFilePinned(file.file_id),
                'menu-open': openFileActionMenuId === file.file_id,
              }"
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
                <button type="button" @click="toggleFilePin(file)">
                  <AppIcon name="push_pin" />
                  {{ isFilePinned(file.file_id) ? 'Unpin' : 'Pin' }}
                </button>
                <button type="button" @click="renameFilePrompt(file)">
                  <AppIcon name="edit" />
                  Rename
                </button>
                <button type="button" class="danger-text" @click="requestDeleteFile(file)">
                  <AppIcon name="close" />
                  Delete
                </button>
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
                        <AppIcon :name="documentSummary ? 'refresh' : 'bolt'" />
                        {{
                          isSummaryLoading
                            ? 'Generating...'
                            : documentSummary
                              ? 'Regenerate'
                              : 'Generate Summary'
                        }}
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

                  <div v-if="documentSummary" class="topic-toolbar">
                    <span>Keywords & Tags</span>
                    <button type="button">+ Add Tag</button>
                  </div>
                  <div v-if="documentSummary" class="topic-list">
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
                    @click="runWorkspaceAction(() => selectSheet(sheet))"
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
                      @click="runWorkspaceAction(() => selectSheet(sheet))"
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
      </section>

      <section v-else class="analysis-page" :style="chatWorkspaceStyle">
        <aside class="chat-session-rail excelai-side-nav">
          <div class="chat-rail-brand">
            <div class="rail-logo">
              <AppIcon name="analytics" />
            </div>
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
            <AppIcon name="add" />
            <strong>New Chat</strong>
          </button>

          <div class="session-section-head">
            <span>Recent</span>
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
              <span class="session-glyph">
                <AppIcon name="chat_bubble" />
              </span>
              <span class="session-copy">
                <strong>{{ session.title }}</strong>
              </span>
              <span class="session-actions" @click.stop>
                <button
                  type="button"
                  class="menu-trigger compact"
                  :aria-expanded="openChatSessionActionMenuId === session.session_id"
                  aria-label="Session actions"
                  @click="toggleChatSessionActionMenu(session.session_id)"
                >
                  <AppIcon name="more_vert" />
                </button>
              </span>
              <span
                v-if="openChatSessionActionMenuId === session.session_id"
                class="item-action-menu session-action-menu"
                @click.stop
              >
                <button type="button" @click="toggleChatSessionPin(session)">
                  <AppIcon name="push_pin" />
                  {{ session.pinned_at ? 'Unpin' : 'Pin' }}
                </button>
                <button type="button" @click="renameChatSessionPrompt(session)">
                  <AppIcon name="edit" />
                  Rename
                </button>
                <button type="button" class="danger-text" @click="removeChatSession(session)">
                  <AppIcon name="close" />
                  Delete
                </button>
              </span>
            </article>

            <div v-if="chatSessions.length === 0" class="session-empty-state">
              No chat sessions yet.
            </div>
          </div>

          <p v-if="chatSessionError" class="error-note session-error">{{ chatSessionError }}</p>

          <div class="rail-system-links">
            <button type="button" disabled>
              <AppIcon name="history" />
              <span>History</span>
            </button>
            <button type="button" @click="setActiveView('files')">
              <AppIcon name="folder_open" />
              <span>Files</span>
            </button>
            <button type="button" disabled>
              <AppIcon name="settings" />
              <span>Settings</span>
            </button>
          </div>

          <div class="chat-rail-user">
            <img
              alt="User profile"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuCydg9xLa1V1jLmz2zCEqipeHRQX6jNRFmnvrbvDd1087ZqFBiMN2m1WqUS7eiTRlcTPGlA-AXESHcNu2x3iBZc1wI_ehf6OJReBuSe9QPBEE4Ii9Cdz6LPcEYHIrJzk4ZitvvROTavnO5XvMCyCvOpEs_GCfqkaNMjx-5vMQXTyOjMIJAvAdoxzX-SvCHKsmXA7ciOdVwuZEtN2TGlzfvKAbf3QZnikct32nv9K3teVaruCd7nFPTVaEgfdt0PJa0sKECq8RA0JBRw"
            />
            <div>
              <strong>Alex Rivera</strong>
              <span>Pro Tier</span>
            </div>
          </div>
        </aside>

        <section class="sheet-stage">
          <div class="workbook-title-bar" aria-label="Current workbook">
            <span class="workbook-title-icon">
              <AppIcon name="description" />
            </span>
            <div class="workbook-title-copy">
              <span>Current Workbook</span>
              <strong :title="selectedFileDisplayName">{{ selectedFileDisplayName }}</strong>
            </div>
            <span class="workbook-title-meta">{{ workbookStatusLabel }}</span>
          </div>

          <header class="sheet-topbar">
            <div class="sheet-search-field">
              <AppIcon name="search" />
              <input
                v-model="searchTerm"
                type="search"
                placeholder="Search data..."
              />
            </div>
            <div class="sheet-topbar-actions">
              <button type="button" aria-label="Notifications">
                <AppIcon name="notifications" />
              </button>
            </div>
          </header>

          <div class="excel-focus-bar">
            <div class="active-cell-pill">
              <AppIcon name="grid_view" />
              <strong>{{ selectedCellAddress }}</strong>
            </div>
            <span class="focus-divider"></span>
            <span class="value-label">Value:</span>
            <div class="active-cell-value-scroll custom-scrollbar" tabindex="0">
              <strong class="active-cell-value">{{ selectedCellValue }}</strong>
            </div>
          </div>

          <div class="excel-grid-shell custom-scrollbar">
            <div
              v-if="preview"
              class="excel-grid-card"
              :class="{
                'column-resizing': isExcelColumnResizing,
                'row-resizing': isExcelRowResizing,
              }"
              :style="excelGridStyle"
            >
              <div class="excel-grid-header-row">
                <div class="excel-grid-corner">
                  <AppIcon name="grid_view" />
                </div>
                <div
                  v-for="(label, labelIndex) in excelColumnLabels"
                  :key="`column-${label}`"
                  class="excel-grid-column-head"
                  @pointerdown="startExcelColumnResizeFromHeader($event, labelIndex + 1)"
                >
                  {{ label }}
                  <span
                    class="excel-column-resize-handle"
                    aria-hidden="true"
                    @pointerdown="startExcelColumnResize($event, labelIndex + 1)"
                  ></span>
                </div>
              </div>

              <div
                v-for="(row, rowIndex) in excelDisplayRows"
                :id="rowDomId(row[0])"
                :key="`${row[0] || rowIndex}-${preview?.offset ?? 0}`"
                class="excel-grid-row"
                :class="{
                  highlighted: rowIsHighlighted(row),
                  'header-like': (preview?.offset ?? 0) === 0 && rowIndex === 0,
                }"
                :style="getExcelRowStyle(row, rowIndex)"
              >
                <div class="excel-grid-row-number">
                  {{ (preview?.offset ?? 0) + rowIndex + 1 }}
                  <span
                    class="excel-row-resize-handle"
                    aria-hidden="true"
                    @pointerdown="startExcelRowResize($event, excelRowKey(row, rowIndex))"
                  ></span>
                </div>
                <div
                  v-for="columnIndex in excelDataColumnCount"
                  :key="`${row[0] || rowIndex}-${columnIndex}`"
                  class="excel-grid-cell"
                  :class="{
                    'cell-selected': isGridCellSelected(row, rowIndex, columnIndex),
                  }"
                  @click="selectGridCell(row, rowIndex, columnIndex)"
                >
                  <span class="excel-grid-cell-value custom-scrollbar">
                    {{ getGridCellValue(row, columnIndex) }}
                  </span>
                </div>
              </div>

              <div
                v-for="fillerIndex in excelFillerRowCount"
                :key="`filler-${fillerIndex}`"
                class="excel-grid-row filler"
                :style="getFillerExcelRowStyle(fillerIndex)"
              >
                <div class="excel-grid-row-number">
                  {{ fillerRowNumber(fillerIndex) }}
                  <span
                    class="excel-row-resize-handle"
                    aria-hidden="true"
                    @pointerdown="startExcelRowResize($event, fillerExcelRowKey(fillerIndex))"
                  ></span>
                </div>
                <div
                  v-for="columnIndex in excelDataColumnCount"
                  :key="`filler-${fillerIndex}-${columnIndex}`"
                  class="excel-grid-cell"
                ></div>
              </div>
            </div>

            <div v-if="!preview" class="excel-grid-empty">
              <span class="excel-grid-empty-icon"><AppIcon name="grid_view" /></span>
              <strong>No workbook selected</strong>
              <p>Start a chat or choose a data source to preview its rows here.</p>
            </div>
          </div>

          <div class="sheet-tabs" aria-label="Workbook sheets">
            <button
              v-for="sheet in sheets"
              :key="sheet.sheet_id"
              type="button"
              :class="{ active: sheet.sheet_id === selectedSheetId }"
              @click="runWorkspaceAction(() => selectSheet(sheet))"
            >
              {{ sheet.sheet_name }}
            </button>
          </div>
        </section>

        <aside class="assistant-column" :class="{ resizing: isChatResizing }">
          <button
            type="button"
            class="chat-column-resizer"
            aria-label="Resize chat panel"
            @pointerdown="startChatResize"
          >
            <AppIcon name="drag_handle" />
          </button>
          <ChatPanel
            :session-id="activeChatSessionId"
            :session-title="activeChatSession?.title ?? ''"
            :router-provider="routerProvider || null"
            :router-model="routerModel || null"
            :answer-provider="answerProvider || null"
            :answer-model="answerModel || null"
            :document-titles="documentTitleMap"
            :active-document="activeDocumentForChat"
            @answer-received="handleChatAnswer"
            @select-citation="handleCitationSelected"
            @select-document="openReferencedDocument"
            @session-created="handleChatSessionCreated"
            @session-title-suggested="handleChatSessionTitleSuggested"
          />
        </aside>
      </section>
    </section>

    <div v-if="transientToastMessage" class="app-toast" role="status">
      {{ transientToastMessage }}
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
          <button
            type="submit"
            class="dialog-primary"
            :disabled="isWorkspaceBusy || isChatSessionLoading"
          >
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
            :disabled="isWorkspaceBusy || isChatSessionLoading"
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

    <section
      v-if="uploadDialog"
      class="dialog-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-dialog-title"
      @keydown.esc="cancelUploadDialog"
    >
      <div class="app-dialog upload-confirm-dialog">
        <div class="dialog-heading">
          <div>
            <p class="eyebrow">
              {{ uploadDialog.kind === 'replace' ? 'Replacement' : 'Upload' }}
            </p>
            <h3 id="upload-dialog-title">
              {{ uploadDialog.kind === 'replace' ? 'Confirm replacement' : 'Upload and parse' }}
            </h3>
          </div>
          <button
            type="button"
            class="dialog-icon-button"
            aria-label="Close"
            @click="cancelUploadDialog"
          >
            <AppIcon name="close" />
          </button>
        </div>
        <div class="upload-dialog-file">
          <span class="file-badge large"><AppIcon name="table_chart" /></span>
          <div>
            <strong>{{ uploadDialog.file.name }}</strong>
            <span>{{ uploadDialog.kind === 'replace' ? 'Create a new active version' : 'Parse workbook into searchable sheets' }}</span>
          </div>
        </div>
        <p v-if="uploadDialog.kind === 'replace'" class="dialog-copy">
          A file with this name already exists. Confirming will keep the workbook record and create a new active version.
        </p>
        <p v-if="dialogError" class="dialog-error">{{ dialogError }}</p>
        <div class="dialog-actions">
          <button type="button" class="dialog-secondary" @click="cancelUploadDialog">Cancel</button>
          <button
            type="button"
            class="dialog-primary"
            :disabled="isWorkspaceBusy"
            @click="confirmUploadDialog"
          >
            {{ isWorkspaceBusy ? 'Parsing...' : uploadDialog.kind === 'replace' ? 'Replace' : 'Upload' }}
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
