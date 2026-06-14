<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  createUploadTask,
  deleteExcelFile,
  ExcelWorkspaceApiError,
  listExcelFiles,
  listExcelSheets,
  listExcelVersions,
  lookupExcelRow,
  previewExcelSheet,
  renameExcelFile,
  searchExcelVersionRows,
  setExcelFileVisibility,
} from '../api/excel-assets-api'
import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  renameChatSession,
  setChatSessionPinned,
} from '../api/chat-api'
import { getCurrentUser, logout as logoutSession } from '../api/auth-api'
import { clearAuthToken } from '../api/auth-token'
import {
  generateDocumentSummary,
  getDocumentSummary,
  updateDocumentSummary,
} from '../api/document-summaries-api'
import { getLlmModelOptions, getLlmPreference, saveLlmPreference } from '../api/llm-api'
import { getWorkspaceConfig } from '../api/workspace-api'
import AppIcon from '../components/AppIcon.vue'
import AuthPanel from '../components/AuthPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import SheetSearchResults from '../components/SheetSearchResults.vue'
import {
  FileInsightPane,
  FilePreviewPanel,
  FileSchemaPanel,
  FileSourcePanel,
  FileSummaryPanel,
  WorkbookUploadDialog,
  useUploadTaskPolling,
  type FileSchemaColumn,
  type ModelStageDraft,
} from '../features/file-management'
import { useTransientFeedback } from './use-transient-feedback'
import {
  defaultExcelCellWidth,
  defaultExcelRowHeight,
  fallbackAllowedUploadExtensions,
  fallbackMaxUploadBytes,
  filePageSize,
  maxChatColumnWidth,
  maxExcelCellWidth,
  maxExcelRowHeight,
  minChatColumnWidth,
  minExcelCellWidth,
  minExcelRowHeight,
  pinnedFileStorageKey,
  previewLimit,
  primaryNavItems,
  sheetSearchLimit,
} from './workspace-constants'
import {
  buildUploadAcceptValue,
  clamp,
  columnLabel,
  csvEscape,
  formatBytes,
  formatSupportedExtensions,
  isAllowedUploadFile,
  rowDomId,
  toErrorMessage,
} from './workspace-utils'
import type { AuthResponse, AuthUser } from '../types/auth'
import type { ChatAnswer, ChatSession, ExcelCitation, SelectedDocument } from '../types/chat'
import type { DocumentSummary, DocumentSummaryUpdate } from '../types/document-summary'
import type { LlmModelDefaults, LlmProviderOption } from '../types/llm'
import type {
  ExcelFile,
  ExcelFileVersion,
  ExcelSheet,
  RowLookupResponse,
  SheetSearchMatch,
  SheetPreviewResponse,
  UploadTaskResponse,
} from '../types/excel-assets'
import type {
  ActiveView,
  ConfirmDialog,
  FileInsightTab,
  ModelStage,
  PrimaryNavItem,
  RenameDialog,
  SelectedCell,
  SelectSheetOptions,
  UploadDialog,
} from './workspace-types'

const initialActiveView: ActiveView =
  typeof window !== 'undefined' && window.location.hash === '#files' ? 'files' : 'chat'

const activeView = ref<ActiveView>(initialActiveView)
const currentUser = ref<AuthUser | null>(null)
const isAuthChecking = ref<boolean>(true)
const authErrorMessage = ref<string>('')
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
const openFileActionMenuId = ref<string>('')
const openChatSessionActionMenuId = ref<string>('')
const {
  feedback: operationFeedback,
  show: showOperationFeedback,
  clear: clearOperationFeedback,
} = useTransientFeedback(3200)
const {
  feedback: chatSessionFeedback,
  show: showChatSessionFeedback,
  clear: clearChatSessionFeedback,
} = useTransientFeedback(2800)
const {
  uploadTask,
  isUploadTaskPending,
  setUploadTask,
  clearUploadTask,
  pollUploadTask,
} = useUploadTaskPolling()
const fileSearchTerm = ref<string>('')
const documentSearchTerm = ref<string>('')
const sheetSearchTerm = ref<string>('')
const sheetSearchResults = ref<SheetSearchMatch[]>([])
const sheetSearchTotal = ref<number>(0)
const sheetSearchError = ref<string>('')
const uploadMaxBytes = ref<number>(fallbackMaxUploadBytes)
const uploadAllowedExtensions = ref<string[]>([...fallbackAllowedUploadExtensions])
const isWorkspaceBusy = ref<boolean>(false)
const isSummaryLoading = ref<boolean>(false)
const isSummarySaving = ref<boolean>(false)
const isLookupLoading = ref<boolean>(false)
const isSheetSearchLoading = ref<boolean>(false)
const availableLlmModels = ref<string[]>([])
const availableLlmProviders = ref<LlmProviderOption[]>([])
const summaryProvider = ref<string>('siliconflow')
const summaryModel = ref<string>('')
const routerProvider = ref<string>('siliconflow')
const routerModel = ref<string>('')
const answerProvider = ref<string>('siliconflow')
const answerModel = ref<string>('')
const draftSummaryProvider = ref<string>('siliconflow')
const draftSummaryModel = ref<string>('')
const draftRouterProvider = ref<string>('siliconflow')
const draftRouterModel = ref<string>('')
const draftAnswerProvider = ref<string>('siliconflow')
const draftAnswerModel = ref<string>('')
const isModelPreferenceSaving = ref<boolean>(false)
const modelPreferenceFeedback = ref<string>('')
const modelPreferenceFeedbackKind = ref<'success' | 'error'>('success')
const pinnedFileIds = ref<string[]>(loadPinnedFileIds())
const selectedCell = ref<SelectedCell | null>(null)
const excelColumnWidths = ref<Record<string, number>>({})
const excelRowHeights = ref<Record<string, number>>({})
const chatColumnWidth = ref<number>(420)
const isChatResizing = ref<boolean>(false)
const isExcelColumnResizing = ref<boolean>(false)
const isExcelRowResizing = ref<boolean>(false)
const isChatPanelCollapsed = ref<boolean>(false)
const isChatAnswerPending = ref<boolean>(false)
const filePage = ref<number>(1)
let excelResizeStartX = 0
let excelResizeStartY = 0
let excelResizeStartWidth = 0
let excelResizeStartHeight = 0
let excelResizeTargetColumnKey = ''
let excelResizeTargetRowKey = ''
let fileListRequestId = 0
let workspaceSelectionRequestId = 0
let rowLookupRequestId = 0
let summaryGenerationRequestId = 0
let summarySaveRequestId = 0
let chatSessionListRequestId = 0
let workspaceBusyRequestId = 0
let sheetSearchRequestId = 0
let previewAbortController: AbortController | null = null
let sheetSearchAbortController: AbortController | null = null
let rowLookupAbortController: AbortController | null = null

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
  const query = fileSearchTerm.value.trim().toLowerCase()
  const visibleFiles = !query
    ? files.value
    : files.value.filter((file) => file.display_name.toLowerCase().includes(query))
  return sortFilesForDisplay(visibleFiles)
})

const filePageCount = computed(() => {
  return Math.max(1, Math.ceil(filteredFiles.value.length / filePageSize))
})

const paginatedFiles = computed(() => {
  const start = (normalizedFilePage.value - 1) * filePageSize
  return filteredFiles.value.slice(start, start + filePageSize)
})

const normalizedFilePage = computed(() => {
  return clamp(filePage.value, 1, filePageCount.value)
})

const visibleFilePages = computed(() => {
  if (filteredFiles.value.length === 0) {
    return []
  }
  const total = filePageCount.value
  const current = normalizedFilePage.value
  const start = clamp(current - 1, 1, Math.max(1, total - 2))
  const end = Math.min(total, start + 2)
  return Array.from({ length: end - start + 1 }, (_value, index) => start + index)
})

const filePaginationLabel = computed(() => {
  const total = filteredFiles.value.length
  if (total === 0) {
    return '0 of 0'
  }
  const start = (normalizedFilePage.value - 1) * filePageSize + 1
  const end = Math.min(total, start + filePageSize - 1)
  return `${start}-${end} of ${total}`
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
  return selectedFile.value?.display_name ?? 'No document selected'
})

const workbookStatusLabel = computed(() => {
  if (!selectedFile.value) {
    return 'No active document'
  }
  const sheetLabel = selectedSheet.value?.sheet_name ?? 'No sheet selected'
  return `${sheetLabel} / ${previewRangeLabel.value}`
})

const selectedCellAddress = computed(() => selectedCell.value?.address ?? 'C5')

const selectedCellValue = computed(() => selectedCell.value?.value || '-')

const chatWorkspaceStyle = computed(() => ({
  '--chat-column-width': `${chatColumnWidth.value}px`,
}))

const chatWorkspaceClasses = computed(() => ({
  'chat-panel-collapsed': isChatPanelCollapsed.value,
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

const sheetSearchMatchColumnMap = computed(() => {
  return new Map(
    sheetSearchResults.value.map((match) => [
      match.mapping.row_id,
      new Set(match.matched_columns),
    ]),
  )
})

const sheetSearchSummary = computed(() => {
  if (isSheetSearchLoading.value) {
    return 'Searching...'
  }
  if (!sheetSearchTerm.value.trim()) {
    return ''
  }
  if (sheetSearchError.value) {
    return sheetSearchError.value
  }
  if (sheetSearchTotal.value === 0) {
    return 'No matches'
  }
  return `${sheetSearchTotal.value} match${sheetSearchTotal.value === 1 ? '' : 'es'}`
})

const uploadAcceptValue = computed(() => buildUploadAcceptValue(uploadAllowedExtensions.value))

const uploadHelpText = computed(() => {
  return `Supports ${formatSupportedExtensions(uploadAllowedExtensions.value)} (Max ${formatBytes(uploadMaxBytes.value)})`
})

const modelStageDrafts = computed<ModelStageDraft[]>(() => [
  {
    stage: 'summary',
    label: 'Summary Model',
    provider: draftSummaryProvider.value,
    model: draftSummaryModel.value,
    modelOptions: modelsForProvider(draftSummaryProvider.value),
  },
  {
    stage: 'router',
    label: 'Router Model',
    provider: draftRouterProvider.value,
    model: draftRouterModel.value,
    modelOptions: modelsForProvider(draftRouterProvider.value),
  },
  {
    stage: 'answer',
    label: 'Chat Model',
    provider: draftAnswerProvider.value,
    model: draftAnswerModel.value,
    modelOptions: modelsForProvider(draftAnswerProvider.value),
  },
])

const schemaColumns = computed<FileSchemaColumn[]>(() => {
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
    reason: 'Current document',
    confidence: null,
  }
})

const activeChatSession = computed(() => {
  return (
    chatSessions.value.find((session) => session.session_id === activeChatSessionId.value) ??
    null
  )
})

const answerSupportsDeepThinking = computed(() => {
  const provider = availableLlmProviders.value.find(
    (item) => item.provider === answerProvider.value,
  )
  return provider?.deep_thinking_models.includes(answerModel.value) ?? false
})

const hasModelPreferenceDraftChanges = computed(() => {
  return (
    draftSummaryProvider.value !== summaryProvider.value ||
    draftSummaryModel.value !== summaryModel.value ||
    draftRouterProvider.value !== routerProvider.value ||
    draftRouterModel.value !== routerModel.value ||
    draftAnswerProvider.value !== answerProvider.value ||
    draftAnswerModel.value !== answerModel.value
  )
})

const canSaveModelPreference = computed(() => {
  return hasModelPreferenceDraftChanges.value && isCompleteModelPreference()
})

const isAdmin = computed(() => currentUser.value?.role === 'admin')

const visiblePrimaryNavItems = computed(() => {
  return primaryNavItems.filter((item) => item.key !== 'files' || isAdmin.value)
})

const userEmail = computed(() => currentUser.value?.email ?? '')

const userRoleLabel = computed(() => (isAdmin.value ? 'Administrator' : 'Workspace user'))

const blocksWorkspaceMutation = computed(() => isChatAnswerPending.value)


onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', syncActiveViewFromLocation)
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('pointerdown', handleDocumentPointerDown)
  }
  void restoreAuthentication()
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('hashchange', syncActiveViewFromLocation)
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('pointerdown', handleDocumentPointerDown)
  }
  clearOperationFeedback()
  clearChatSessionFeedback()
  stopChatResize()
  stopExcelColumnResize()
  stopExcelRowResize()
  abortWorkspaceReadRequests()
})

watch(
  () => filteredFiles.value.length,
  () => {
    filePage.value = 1
    closeActionMenus()
  },
)

async function initializeWorkspace(): Promise<void> {
  if (!currentUser.value) {
    return
  }
  if (!isAdmin.value && activeView.value === 'files') {
    setActiveView('chat')
  }
  await loadWorkspaceConfig()
  await loadLlmModelOptions()
  await loadChatSessions()
  await refreshFiles()
}

async function loadWorkspaceConfig(): Promise<void> {
  try {
    const config = await getWorkspaceConfig()
    uploadMaxBytes.value = config.upload.max_bytes
    uploadAllowedExtensions.value = config.upload.supported_extensions.length > 0
      ? config.upload.supported_extensions
      : [...fallbackAllowedUploadExtensions]
  } catch {
    uploadMaxBytes.value = fallbackMaxUploadBytes
    uploadAllowedExtensions.value = [...fallbackAllowedUploadExtensions]
  }
}

async function restoreAuthentication(): Promise<void> {
  authErrorMessage.value = ''
  isAuthChecking.value = true
  try {
    currentUser.value = await getCurrentUser()
    await initializeWorkspace()
  } catch (error: unknown) {
    clearAuthToken()
    currentUser.value = null
    authErrorMessage.value = error instanceof ExcelWorkspaceApiError && error.statusCode === 401
      ? ''
      : toErrorMessage(error)
  } finally {
    isAuthChecking.value = false
  }
}

async function handleAuthenticated(response: AuthResponse): Promise<void> {
  clearAuthToken()
  currentUser.value = response.user
  authErrorMessage.value = ''
  await resetWorkspaceState()
  await initializeWorkspace()
}

async function signOut(): Promise<void> {
  try {
    await logoutSession()
  } catch {
    // Local state cleanup remains the fallback if the server session is already gone.
  }
  clearAuthToken()
  currentUser.value = null
  await resetWorkspaceState()
}

async function resetWorkspaceState(): Promise<void> {
  chatSessions.value = []
  activeChatSessionId.value = ''
  files.value = []
  versions.value = []
  sheets.value = []
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  latestAnswer.value = null
  selectedFileId.value = ''
  selectedVersionId.value = ''
  selectedSheetId.value = ''
  selectedCell.value = null
  clearUploadTask()
  clearSheetSearch()
  clearWorkspaceError()
  chatSessionError.value = ''
  isChatAnswerPending.value = false
  closeActionMenus()
}

async function loadLlmModelOptions(): Promise<void> {
  const options = await getLlmModelOptions()
  availableLlmModels.value = options.models
  availableLlmProviders.value = options.providers
  applyModelDefaults(options.defaults)
  try {
    const preference = await getLlmPreference()
    applyModelDefaults(preference)
  } catch (error: unknown) {
    showWorkspaceError(error)
  }
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
  resetModelPreferenceDraft()
}

function setActiveView(view: ActiveView): void {
  if (view === 'files' && !isAdmin.value) {
    activeView.value = 'chat'
    return
  }
  closeActionMenus()
  if (view !== 'files') {
    isFileInsightFullscreen.value = false
  }
  activeView.value = view
  if (typeof window !== 'undefined') {
    window.history.replaceState(null, '', view === 'chat' ? '#chat' : '#files')
  }
}

function selectPrimaryNavItem(item: PrimaryNavItem): void {
  if (item.disabled || item.key === 'settings') {
    return
  }
  setActiveView(item.key)
}

function syncActiveViewFromLocation(): void {
  if (typeof window === 'undefined') {
    return
  }
  const nextView: ActiveView = window.location.hash === '#files' ? 'files' : 'chat'
  if (nextView === 'files' && !isAdmin.value) {
    setActiveView('chat')
    return
  }
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

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!openFileActionMenuId.value && !openChatSessionActionMenuId.value) {
    return
  }
  if (isActionMenuTarget(event.target)) {
    return
  }
  closeActionMenus()
}

function isActionMenuTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('.item-action-menu, .menu-trigger'))
}

function setFilePage(page: number): void {
  filePage.value = clamp(page, 1, filePageCount.value)
  closeActionMenus()
}

function stepFilePage(direction: -1 | 1): void {
  setFilePage(normalizedFilePage.value + direction)
}

function collapseChatPanel(): void {
  stopChatResize()
  isChatPanelCollapsed.value = true
}

function expandChatPanel(): void {
  isChatPanelCollapsed.value = false
}

function showNotificationsNotice(): void {
  showOperationFeedback('info', 'No new file notifications.')
}

function showWorkspaceError(error: unknown, durationMs = 4200): void {
  showOperationFeedback('error', toErrorMessage(error), durationMs)
}

function showWorkspaceErrorMessage(message: string, durationMs = 4200): void {
  showOperationFeedback('error', message, durationMs)
}

function clearWorkspaceError(): void {
  clearOperationFeedback()
}

async function loadChatSessions(preferredSessionId: string | null = null): Promise<void> {
  const requestId = ++chatSessionListRequestId
  chatSessionError.value = ''
  clearChatSessionFeedback()
  isChatSessionLoading.value = true
  try {
    const sessions = await listChatSessions()
    if (requestId !== chatSessionListRequestId) {
      return
    }
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
    if (requestId === chatSessionListRequestId) {
      chatSessionError.value = toErrorMessage(error)
    }
  } finally {
    if (requestId === chatSessionListRequestId) {
      isChatSessionLoading.value = false
    }
  }
}

async function startNewChatSession(): Promise<void> {
  closeActionMenus()
  chatSessionError.value = ''
  clearChatSessionFeedback()
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
  const pinned = !session.pinned_at
  await updateChatSession(
    () => setChatSessionPinned(session.session_id, pinned),
    pinned ? 'Chat pinned.' : 'Chat unpinned.',
  )
}

async function removeChatSession(session: ChatSession): Promise<void> {
  closeActionMenus()
  dialogError.value = ''
  confirmDialog.value = { kind: 'session', session }
}

async function confirmDeleteChatSession(session: ChatSession): Promise<void> {
  chatSessionError.value = ''
  clearChatSessionFeedback()
  isChatSessionLoading.value = true
  try {
    await deleteChatSession(session.session_id)
    confirmDialog.value = null
    chatSessions.value = chatSessions.value.filter(
      (item) => item.session_id !== session.session_id,
    )
    if (activeChatSessionId.value === session.session_id) {
      activeChatSessionId.value = chatSessions.value[0]?.session_id ?? ''
      latestAnswer.value = null
    }
    showChatSessionFeedback('success', 'Chat deleted.')
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

async function updateChatSession(
  action: () => Promise<ChatSession>,
  successMessage = '',
): Promise<void> {
  chatSessionError.value = ''
  clearChatSessionFeedback()
  isChatSessionLoading.value = true
  try {
    const session = await action()
    upsertChatSession(session)
    if (successMessage) {
      showChatSessionFeedback('success', successMessage)
    }
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
}

async function toggleFileVisibility(file: ExcelFile): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  closeActionMenus()
  const busyRequestId = beginWorkspaceBusy()
  clearWorkspaceError()
  try {
    const updatedFile = await setExcelFileVisibility(
      file.file_id,
      !file.visible_to_members,
    )
    files.value = files.value.map((item) => (
      item.file_id === updatedFile.file_id ? updatedFile : item
    ))
  } catch (error: unknown) {
    showWorkspaceError(error)
  } finally {
    finishWorkspaceBusy(busyRequestId)
  }
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

function nextWorkspaceSelectionRequestId(): number {
  workspaceSelectionRequestId += 1
  return workspaceSelectionRequestId
}

function isCurrentWorkspaceSelection(requestId: number): boolean {
  return requestId === workspaceSelectionRequestId
}

function beginWorkspaceBusy(): number {
  workspaceBusyRequestId += 1
  isWorkspaceBusy.value = true
  return workspaceBusyRequestId
}

function finishWorkspaceBusy(requestId: number): void {
  if (requestId === workspaceBusyRequestId) {
    isWorkspaceBusy.value = false
  }
}

async function refreshFiles(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const requestId = ++fileListRequestId
  const busyRequestId = beginWorkspaceBusy()
  clearWorkspaceError()
  try {
    const nextFiles = await listExcelFiles()
    if (requestId !== fileListRequestId) {
      return
    }
    files.value = nextFiles
    const selectedStillExists = files.value.some((file) => file.file_id === selectedFileId.value)
    if (!selectedStillExists) {
      nextWorkspaceSelectionRequestId()
      clearSelection()
    }
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0])
    }
  } catch (error: unknown) {
    if (requestId === fileListRequestId) {
      showWorkspaceError(error)
    }
  } finally {
    if (requestId === fileListRequestId) {
      finishWorkspaceBusy(busyRequestId)
    }
  }
}

async function chooseFile(file: ExcelFile, view: ActiveView | null = null): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  closeActionMenus()
  clearWorkspaceError()
  const requestId = nextWorkspaceSelectionRequestId()
  const busyRequestId = beginWorkspaceBusy()
  try {
    await selectFile(file, requestId)
    if (view) {
      setActiveView(view)
    }
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      showWorkspaceError(error)
    }
  } finally {
    finishWorkspaceBusy(busyRequestId)
  }
}

async function selectFile(
  file: ExcelFile,
  requestId = nextWorkspaceSelectionRequestId(),
): Promise<void> {
  if (!isCurrentWorkspaceSelection(requestId)) {
    return
  }
  selectedFileId.value = file.file_id
  selectedVersionId.value = ''
  selectedSheetId.value = ''
  abortWorkspaceReadRequests()
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  selectedCell.value = null
  clearSheetSearch()
  const nextVersions = await listExcelVersions(file.file_id)
  if (!isCurrentWorkspaceSelection(requestId) || selectedFileId.value !== file.file_id) {
    return
  }
  versions.value = nextVersions
  const targetVersionId = file.active_version_id ?? versions.value[0]?.version_id ?? ''
  if (targetVersionId) {
    await selectVersion(targetVersionId, requestId)
  } else {
    sheets.value = []
  }
}

async function selectVersion(
  versionId: string,
  requestId = nextWorkspaceSelectionRequestId(),
): Promise<void> {
  if (!isCurrentWorkspaceSelection(requestId)) {
    return
  }
  if (!versionId) {
    selectedVersionId.value = ''
    sheets.value = []
    preview.value = null
    rowLookup.value = null
    documentSummary.value = null
    clearSheetSearch()
    return
  }
  selectedVersionId.value = versionId
  selectedSheetId.value = ''
  abortWorkspaceReadRequests()
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  selectedCell.value = null
  clearSheetSearch()
  const [nextSheets, nextSummary] = await Promise.all([
    listExcelSheets(versionId),
    getDocumentSummary(versionId).catch(() => null),
  ])
  if (!isCurrentWorkspaceSelection(requestId) || selectedVersionId.value !== versionId) {
    return
  }
  sheets.value = nextSheets
  documentSummary.value = nextSummary
  if (nextSheets[0]) {
    await selectSheet(nextSheets[0], requestId)
  }
}

async function selectCurrentVersion(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  if (selectedVersionId.value) {
    await runWorkspaceAction((requestId) => selectVersion(selectedVersionId.value, requestId))
  }
}

async function handlePreviewVersionChange(versionId: string): Promise<void> {
  selectedVersionId.value = versionId
  await selectCurrentVersion()
}

async function selectCurrentSheet(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const sheet = sheets.value.find((item) => item.sheet_id === selectedSheetId.value)
  if (sheet) {
    await runWorkspaceAction((requestId) => selectSheet(sheet, requestId))
  }
}

async function handlePreviewSheetChange(sheetId: string): Promise<void> {
  selectedSheetId.value = sheetId
  await selectCurrentSheet()
}

function setSheetSearchTerm(term: string): void {
  sheetSearchTerm.value = term
}

function selectInsightSheet(sheet: ExcelSheet): void {
  void runWorkspaceAction((requestId) => selectSheet(sheet, requestId))
}

async function selectSheet(
  sheet: ExcelSheet,
  requestId = nextWorkspaceSelectionRequestId(),
  options: SelectSheetOptions = {},
): Promise<void> {
  if (!isCurrentWorkspaceSelection(requestId)) {
    return
  }
  selectedSheetId.value = sheet.sheet_id
  rowLookup.value = null
  selectedCell.value = null
  if (!options.preserveSheetSearch) {
    clearSheetSearch()
  }
  previewAbortController = nextAbortController(previewAbortController)
  const previewSignal = previewAbortController.signal
  const nextPreview = await previewExcelSheet(
    sheet.sheet_id,
    0,
    previewLimit,
    { signal: previewSignal },
  )
  if (!isCurrentWorkspaceSelection(requestId) || selectedSheetId.value !== sheet.sheet_id) {
    return
  }
  preview.value = nextPreview
}

async function loadPreviewPage(offset: number): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  if (!selectedSheetId.value) {
    return
  }
  const requestId = nextWorkspaceSelectionRequestId()
  const sheetId = selectedSheetId.value
  clearWorkspaceError()
  try {
    const safeOffset = Math.max(0, offset)
    rowLookup.value = null
    selectedCell.value = null
    previewAbortController = nextAbortController(previewAbortController)
    const previewSignal = previewAbortController.signal
    const nextPreview = await previewExcelSheet(
      sheetId,
      safeOffset,
      previewLimit,
      { signal: previewSignal },
    )
    if (!isCurrentWorkspaceSelection(requestId) || selectedSheetId.value !== sheetId) {
      return
    }
    preview.value = nextPreview
  } catch (error: unknown) {
    if (isAbortError(error)) {
      return
    }
    if (isCurrentWorkspaceSelection(requestId)) {
      showWorkspaceError(error)
    }
  }
}

async function submitSheetSearch(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const query = sheetSearchTerm.value.trim()
  if (!query) {
    clearSheetSearch()
    return
  }
  if (!selectedVersionId.value) {
    sheetSearchError.value = 'Select a workbook first.'
    return
  }

  const requestId = ++sheetSearchRequestId
  const selectionRequestId = workspaceSelectionRequestId
  const versionId = selectedVersionId.value
  sheetSearchError.value = ''
  isSheetSearchLoading.value = true
  sheetSearchAbortController = nextAbortController(sheetSearchAbortController)
  const searchSignal = sheetSearchAbortController.signal
  try {
    const result = await searchExcelVersionRows(
      versionId,
      query,
      sheetSearchLimit,
      { signal: searchSignal },
    )
    if (!isCurrentSheetSearch(requestId, selectionRequestId, versionId)) {
      return
    }
    sheetSearchTerm.value = result.query
    sheetSearchResults.value = result.matches
    sheetSearchTotal.value = result.total_matches
    const firstMatch = result.matches[0]
    if (firstMatch) {
      await focusSheetSearchMatch(firstMatch)
    }
  } catch (error: unknown) {
    if (isAbortError(error)) {
      return
    }
    if (isCurrentSheetSearch(requestId, selectionRequestId, versionId)) {
      sheetSearchError.value = toErrorMessage(error)
      sheetSearchResults.value = []
      sheetSearchTotal.value = 0
    }
  } finally {
    if (requestId === sheetSearchRequestId) {
      isSheetSearchLoading.value = false
    }
  }
}

async function focusSheetSearchMatch(match: SheetSearchMatch): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const sheet = sheets.value.find((item) => item.sheet_id === match.mapping.sheet_id)
  if (!sheet) {
    sheetSearchError.value = 'Matched sheet is no longer available.'
    return
  }
  const requestId = workspaceSelectionRequestId
  if (selectedSheetId.value !== sheet.sheet_id) {
    await selectSheet(sheet, requestId, { preserveSheetSearch: true })
  }
  if (!isCurrentWorkspaceSelection(requestId) || selectedSheetId.value !== sheet.sheet_id) {
    return
  }
  await lookupRowInSheet(match.mapping.sheet_id, match.mapping.row_id)
}

function clearSheetSearch(): void {
  sheetSearchRequestId += 1
  sheetSearchAbortController?.abort()
  sheetSearchAbortController = null
  sheetSearchTerm.value = ''
  clearSheetSearchResults()
}

function clearSheetSearchResults(): void {
  sheetSearchResults.value = []
  sheetSearchTotal.value = 0
  sheetSearchError.value = ''
  isSheetSearchLoading.value = false
}

function isCurrentSheetSearch(
  requestId: number,
  selectionRequestId: number,
  versionId: string,
): boolean {
  return (
    requestId === sheetSearchRequestId &&
    isCurrentWorkspaceSelection(selectionRequestId) &&
    selectedVersionId.value === versionId
  )
}

function nextAbortController(
  currentController: AbortController | null,
): AbortController {
  currentController?.abort()
  return new AbortController()
}

function isAbortError(error: unknown): boolean {
  return error instanceof ExcelWorkspaceApiError && error.message === 'Request cancelled.'
}

function abortWorkspaceReadRequests(): void {
  previewAbortController?.abort()
  sheetSearchAbortController?.abort()
  rowLookupAbortController?.abort()
  previewAbortController = null
  sheetSearchAbortController = null
  rowLookupAbortController = null
}

async function generateSummaryForSelectedVersion(): Promise<void> {
  if (!selectedVersionId.value) {
    showWorkspaceErrorMessage('Select a version first.')
    return
  }
  const versionId = selectedVersionId.value
  const selectionRequestId = workspaceSelectionRequestId
  const generationRequestId = ++summaryGenerationRequestId
  clearWorkspaceError()
  isSummaryLoading.value = true
  try {
    const nextSummary = await generateDocumentSummary(
      versionId,
    )
    if (
      generationRequestId === summaryGenerationRequestId &&
      isCurrentWorkspaceSelection(selectionRequestId) &&
      selectedVersionId.value === versionId
    ) {
      documentSummary.value = nextSummary
      showOperationFeedback('success', 'Document description generated.')
    }
  } catch (error: unknown) {
    if (
      generationRequestId === summaryGenerationRequestId &&
      isCurrentWorkspaceSelection(selectionRequestId) &&
      selectedVersionId.value === versionId
    ) {
      showWorkspaceError(error)
    }
  } finally {
    if (generationRequestId === summaryGenerationRequestId) {
      isSummaryLoading.value = false
    }
  }
}

async function saveDocumentSummary(
  payload: DocumentSummaryUpdate,
  onSaved: (saved: boolean) => void,
): Promise<void> {
  if (!selectedVersionId.value) {
    showWorkspaceErrorMessage('Select a version first.')
    onSaved(false)
    return
  }
  const versionId = selectedVersionId.value
  const selectionRequestId = workspaceSelectionRequestId
  const saveRequestId = ++summarySaveRequestId
  clearWorkspaceError()
  isSummarySaving.value = true
  try {
    const nextSummary = await updateDocumentSummary(versionId, payload)
    const isCurrentVersion =
      saveRequestId === summarySaveRequestId &&
      isCurrentWorkspaceSelection(selectionRequestId) &&
      selectedVersionId.value === versionId
    if (isCurrentVersion) {
      documentSummary.value = nextSummary
      showOperationFeedback('success', 'Document summary saved.')
    }
    onSaved(isCurrentVersion)
  } catch (error: unknown) {
    if (
      saveRequestId === summarySaveRequestId &&
      isCurrentWorkspaceSelection(selectionRequestId) &&
      selectedVersionId.value === versionId
    ) {
      showWorkspaceError(error)
    }
    onSaved(false)
  } finally {
    if (saveRequestId === summarySaveRequestId) {
      isSummarySaving.value = false
    }
  }
}

function handleUploadFileSelected(file: File | null): void {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  setUploadFile(file)
}

function setUploadFile(file: File | null): void {
  pendingReplaceFile.value = null
  uploadDialog.value = null
  if (!file) {
    selectedUploadFile.value = null
    return
  }
  if (!isAllowedUploadFile(file, uploadAllowedExtensions.value)) {
    selectedUploadFile.value = null
    showWorkspaceErrorMessage(
      `Only these Excel file types are supported: ${formatSupportedExtensions(uploadAllowedExtensions.value)}.`,
    )
    return
  }
  if (file.size > uploadMaxBytes.value) {
    selectedUploadFile.value = null
    showWorkspaceErrorMessage(`File is larger than ${formatBytes(uploadMaxBytes.value)}.`)
    return
  }
  clearWorkspaceError()
  selectedUploadFile.value = file
  uploadDialog.value = { kind: 'new', file }
}

function requestDeleteFile(file: ExcelFile): void {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  closeActionMenus()
  confirmDialog.value = { kind: 'file', file }
  pendingDeleteFile.value = null
  dialogError.value = ''
  clearWorkspaceError()
}

function exportPreviewCsv(): void {
  if (!preview.value || preview.value.rows.length === 0) {
    showWorkspaceErrorMessage('No preview rows are available to download.')
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
}

async function renameFilePrompt(file: ExcelFile): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  closeActionMenus()
  dialogError.value = ''
  renameDialog.value = { kind: 'file', file }
  renameDraft.value = file.display_name
}

function cancelDialog(): void {
  renameDialog.value = null
  confirmDialog.value = null
  uploadDialog.value = null
  clearUploadTask()
  dialogError.value = ''
  renameDraft.value = ''
  selectedUploadFile.value = null
  pendingReplaceFile.value = null
}

function cancelUploadDialog(): void {
  uploadDialog.value = null
  clearUploadTask()
  dialogError.value = ''
  selectedUploadFile.value = null
  pendingReplaceFile.value = null
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
  if (dialog.kind === 'file' && !ensureWorkspaceMutationAllowed()) {
    return
  }

  const trimmedValue = renameDraft.value.trim()
  if (!trimmedValue) {
    dialogError.value =
      dialog.kind === 'file' ? 'Workbook name cannot be empty.' : 'Session title cannot be empty.'
    return
  }

  dialogError.value = ''
  const busyRequestId = dialog.kind === 'file' ? beginWorkspaceBusy() : null
  try {
    if (dialog.kind === 'file') {
      clearWorkspaceError()
      const renamedFile = await renameExcelFile(dialog.file.file_id, trimmedValue)
      files.value = files.value.map((item) => (
        item.file_id === renamedFile.file_id ? renamedFile : item
      ))
      showOperationFeedback('success', `${renamedFile.display_name} renamed.`)
    } else {
      await updateChatSession(
        () => renameChatSession(dialog.session.session_id, trimmedValue),
        'Chat renamed.',
      )
    }
    cancelDialog()
  } catch (error: unknown) {
    dialogError.value = toErrorMessage(error)
  } finally {
    if (busyRequestId !== null) {
      finishWorkspaceBusy(busyRequestId)
    }
  }
}

async function confirmDeleteFile(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const file =
    confirmDialog.value?.kind === 'file' ? confirmDialog.value.file : pendingDeleteFile.value
  if (!file) {
    return
  }

  clearWorkspaceError()
  const requestId = nextWorkspaceSelectionRequestId()
  const busyRequestId = beginWorkspaceBusy()
  try {
    const result = await deleteExcelFile(file.file_id, true)
    pendingDeleteFile.value = null
    confirmDialog.value = null
    if (selectedFileId.value === file.file_id) {
      clearSelection()
    }
    const nextFiles = await listExcelFiles()
    if (!isCurrentWorkspaceSelection(requestId)) {
      return
    }
    files.value = nextFiles
    if (!selectedFileId.value && files.value[0]) {
      await selectFile(files.value[0], requestId)
    }
    showOperationFeedback(
      'success',
      `${result.display_name} removed from file management.`,
      3600,
    )
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingDeleteFile.value = file
      confirmDialog.value = { kind: 'file', file }
      showOperationFeedback('warning', `Confirm deletion for ${file.display_name}.`, 5000)
      return
    }
    if (isCurrentWorkspaceSelection(requestId)) {
      dialogError.value = toErrorMessage(error)
    }
  } finally {
    finishWorkspaceBusy(busyRequestId)
  }
}

async function uploadSelectedFile(replaceExisting = false): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const file = replaceExisting ? pendingReplaceFile.value : selectedUploadFile.value
  if (!file) {
    showWorkspaceErrorMessage('Choose an Excel workbook first.')
    return
  }

  clearWorkspaceError()
  const requestId = nextWorkspaceSelectionRequestId()
  const busyRequestId = beginWorkspaceBusy()
  let taskStarted = false
  try {
    const task = await createUploadTask(file, replaceExisting)
    taskStarted = true
    setUploadTask({
      ...task,
      original_filename: file.name,
      replace_existing: replaceExisting,
      error_message: null,
      started_at: null,
      finished_at: null,
      result: null,
    })
    dialogError.value = ''
    showOperationFeedback('info', `${file.name} upload queued for parsing.`)
    finishWorkspaceBusy(busyRequestId)
    void pollUploadTask(task.task_id, {
      isCurrent: () => isCurrentWorkspaceSelection(requestId),
      onReady: (readyTask) => finishUploadTask(readyTask, requestId),
      onFailure: (message) => {
        dialogError.value = message
      },
      onError: (error) => {
        dialogError.value = toErrorMessage(error)
      },
    })
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingReplaceFile.value = file
      selectedUploadFile.value = null
      uploadDialog.value = { kind: 'replace', file }
      clearUploadTask()
      dialogError.value = ''
      return
    }
    if (isCurrentWorkspaceSelection(requestId)) {
      if (uploadDialog.value) {
        dialogError.value = toErrorMessage(error)
      } else {
        showWorkspaceError(error)
      }
    }
  } finally {
    if (!taskStarted) {
      finishWorkspaceBusy(busyRequestId)
    }
  }
}

async function finishUploadTask(task: UploadTaskResponse, requestId: number): Promise<void> {
  const result = task.result
  if (!result) {
    return
  }
  pendingReplaceFile.value = null
  selectedUploadFile.value = null
  uploadDialog.value = null
  clearUploadTask()
  dialogError.value = ''
  showOperationFeedback('success', `${result.file.display_name} uploaded and parsed.`)
  const nextFiles = await listExcelFiles()
  if (!isCurrentWorkspaceSelection(requestId)) {
    return
  }
  files.value = nextFiles
  const uploadedFile = files.value.find((item) => item.file_id === result.file.file_id)
  if (uploadedFile) {
    await selectFile(uploadedFile, requestId)
  }
}

async function lookupVisibleRow(row: string[]): Promise<void> {
  const rowId = row[0]?.trim()
  if (!rowId || isLookupLoading.value || !ensureWorkspaceMutationAllowed()) {
    return
  }
  await lookupRowInSheet(selectedSheetId.value, rowId)
}

async function lookupRowInSheet(sheetId: string, rowId: string): Promise<void> {
  const requestId = ++rowLookupRequestId
  const selectionRequestId = workspaceSelectionRequestId
  clearWorkspaceError()
  isLookupLoading.value = true
  rowLookupAbortController = nextAbortController(rowLookupAbortController)
  const lookupSignal = rowLookupAbortController.signal
  try {
    const result = await lookupExcelRow(sheetId, rowId, { signal: lookupSignal })
    if (!isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      return
    }
    const nextPreview = await previewForLookupRow(result, lookupSignal)
    if (!isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      return
    }
    if (nextPreview) {
      preview.value = nextPreview
    }
    rowLookup.value = result
    selectedCell.value = null
    await nextTick()
    if (isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      document.getElementById(rowDomId(result.mapping.row_id))?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    }
  } catch (error: unknown) {
    if (isAbortError(error)) {
      return
    }
    if (isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      showWorkspaceError(error)
    }
  } finally {
    if (requestId === rowLookupRequestId) {
      isLookupLoading.value = false
    }
  }
}

function isCurrentRowLookup(
  requestId: number,
  selectionRequestId: number,
  sheetId: string,
): boolean {
  return (
    requestId === rowLookupRequestId &&
    isCurrentWorkspaceSelection(selectionRequestId) &&
    selectedSheetId.value === sheetId
  )
}

async function previewForLookupRow(
  result: RowLookupResponse,
  signal?: AbortSignal,
): Promise<SheetPreviewResponse | null> {
  const rowZeroIndex = Math.max(0, result.mapping.raw_csv_row_number - 1)
  const currentOffset = preview.value?.offset ?? 0
  const currentEnd = currentOffset + (preview.value?.rows.length ?? 0)
  const isCurrentSheetPreview = preview.value?.sheet.sheet_id === result.sheet.sheet_id
  if (!isCurrentSheetPreview || rowZeroIndex < currentOffset || rowZeroIndex >= currentEnd) {
    const centeredOffset = Math.max(0, rowZeroIndex - 24)
    return previewExcelSheet(
      result.sheet.sheet_id,
      centeredOffset,
      previewLimit,
      { signal },
    )
  }
  return null
}

async function handleCitationSelected(citation: ExcelCitation): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  setActiveView('chat')
  clearWorkspaceError()
  const requestId = nextWorkspaceSelectionRequestId()
  try {
    let targetFile = files.value.find((file) => file.file_id === citation.file_id)
    if (!targetFile) {
      const nextFiles = await listExcelFiles()
      if (!isCurrentWorkspaceSelection(requestId)) {
        return
      }
      files.value = nextFiles
      targetFile = files.value.find((file) => file.file_id === citation.file_id)
    }
    if (targetFile && selectedFileId.value !== targetFile.file_id) {
      await selectFile(targetFile, requestId)
    }
    if (selectedVersionId.value !== citation.version_id) {
      await selectVersion(citation.version_id, requestId)
    }
    const targetSheet = sheets.value.find((sheet) => sheet.sheet_id === citation.sheet_id)
    if (targetSheet && selectedSheetId.value !== targetSheet.sheet_id) {
      await selectSheet(targetSheet, requestId)
    }
    if (!isCurrentWorkspaceSelection(requestId)) {
      return
    }
    await lookupRowInSheet(citation.sheet_id, citation.row_id)
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      showWorkspaceError(error)
    }
  }
}

function handleChatAnswer(answer: ChatAnswer): void {
  latestAnswer.value = answer
  void loadChatSessions(activeChatSessionId.value === answer.session_id ? answer.session_id : null)
}

async function openReferencedDocument(document: SelectedDocument): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const requestId = nextWorkspaceSelectionRequestId()
  setActiveView('chat')
  await runWorkspaceAction(async () => {
    const file = files.value.find((item) => item.file_id === document.file_id)
    if (file && selectedFileId.value !== file.file_id) {
      await selectFile(file, requestId)
    }
    if (
      isCurrentWorkspaceSelection(requestId) &&
      selectedVersionId.value !== document.version_id
    ) {
      await selectVersion(document.version_id, requestId)
    }
  }, requestId)
}

async function runWorkspaceAction(
  action: (requestId: number) => Promise<void>,
  requestId = nextWorkspaceSelectionRequestId(),
): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  clearWorkspaceError()
  const busyRequestId = beginWorkspaceBusy()
  try {
    await action(requestId)
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      showWorkspaceError(error)
    }
  } finally {
    finishWorkspaceBusy(busyRequestId)
  }
}

function handleChatAskingStateChanged(value: boolean): void {
  isChatAnswerPending.value = value
}

function ensureWorkspaceMutationAllowed(): boolean {
  if (!blocksWorkspaceMutation.value) {
    return true
  }
  showOperationFeedback('info', 'ExcelAI is answering. Wait for the response before changing files.')
  return false
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
  clearSheetSearch()
}

function rowIsHighlighted(row: string[]): boolean {
  return Boolean(rowLookup.value && row[0] === rowLookup.value.mapping.row_id)
}

function isSheetSearchMatchedCell(row: string[], columnIndex: number): boolean {
  const rowId = row[0]
  if (!rowId) {
    return false
  }
  return sheetSearchMatchColumnMap.value.get(rowId)?.has(columnIndex) ?? false
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

function ensureDraftStageModel(stage: ModelStage): void {
  const provider =
    stage === 'summary'
      ? draftSummaryProvider.value
      : stage === 'router'
        ? draftRouterProvider.value
        : draftAnswerProvider.value
  const models = modelsForProvider(provider)
  if (stage === 'summary' && !models.includes(draftSummaryModel.value)) {
    draftSummaryModel.value = models[0] ?? ''
  }
  if (stage === 'router' && !models.includes(draftRouterModel.value)) {
    draftRouterModel.value = models[0] ?? ''
  }
  if (stage === 'answer' && !models.includes(draftAnswerModel.value)) {
    draftAnswerModel.value = models[0] ?? ''
  }
}

function handleModelProviderChange(stage: ModelStage): void {
  ensureDraftStageModel(stage)
  modelPreferenceFeedback.value = ''
}

function handleModelDraftChange(): void {
  modelPreferenceFeedback.value = ''
}

function updateModelStageProvider(stage: ModelStage, provider: string): void {
  if (stage === 'summary') {
    draftSummaryProvider.value = provider
  } else if (stage === 'router') {
    draftRouterProvider.value = provider
  } else {
    draftAnswerProvider.value = provider
  }
  handleModelProviderChange(stage)
}

function updateModelStageModel(stage: ModelStage, model: string): void {
  if (stage === 'summary') {
    draftSummaryModel.value = model
  } else if (stage === 'router') {
    draftRouterModel.value = model
  } else {
    draftAnswerModel.value = model
  }
  handleModelDraftChange()
}

function resetModelPreferenceDraft(): void {
  draftSummaryProvider.value = summaryProvider.value
  draftSummaryModel.value = summaryModel.value
  draftRouterProvider.value = routerProvider.value
  draftRouterModel.value = routerModel.value
  draftAnswerProvider.value = answerProvider.value
  draftAnswerModel.value = answerModel.value
  modelPreferenceFeedback.value = ''
}

async function saveModelPreferenceDefaults(): Promise<void> {
  if (!isCompleteModelPreference()) {
    modelPreferenceFeedbackKind.value = 'error'
    modelPreferenceFeedback.value = 'Select a provider and model for every stage.'
    return
  }
  isModelPreferenceSaving.value = true
  modelPreferenceFeedback.value = ''
  try {
    const preference = await saveLlmPreference({
      summary_provider: draftSummaryProvider.value,
      summary_model: draftSummaryModel.value,
      router_provider: draftRouterProvider.value,
      router_model: draftRouterModel.value,
      answer_provider: draftAnswerProvider.value,
      answer_model: draftAnswerModel.value,
    })
    applyModelDefaults(preference)
    modelPreferenceFeedbackKind.value = 'success'
    modelPreferenceFeedback.value = 'Saved as workspace defaults.'
  } catch (error: unknown) {
    modelPreferenceFeedbackKind.value = 'error'
    modelPreferenceFeedback.value = toErrorMessage(error)
  } finally {
    isModelPreferenceSaving.value = false
  }
}

function isCompleteModelPreference(): boolean {
  return Boolean(
    draftSummaryProvider.value &&
      draftSummaryModel.value &&
      draftRouterProvider.value &&
      draftRouterModel.value &&
      draftAnswerProvider.value &&
      draftAnswerModel.value,
  )
}

</script>

<template>
  <div v-if="isAuthChecking" class="auth-loading-screen">
    <div class="auth-loading-card">
      <span class="auth-card-icon"><AppIcon name="lock" /></span>
      <strong>Checking session</strong>
    </div>
  </div>
  <AuthPanel
    v-else-if="!currentUser"
    @authenticated="handleAuthenticated"
  />
  <main v-else class="excelai-app" :class="{ 'chat-mode': activeView === 'chat' }">
    <aside class="app-sidebar">
      <div class="brand-block">
        <h1>ExcelAI</h1>
        <p>Researcher Pro</p>
      </div>

      <nav class="primary-nav" aria-label="Primary">
        <button
          v-for="item in visiblePrimaryNavItems"
          :key="item.key"
          type="button"
          class="nav-item"
          :class="{ active: activeView === item.key, 'muted-nav': item.disabled }"
          :disabled="item.disabled"
          :aria-disabled="item.disabled ? 'true' : undefined"
          @click="selectPrimaryNavItem(item)"
        >
          <span class="nav-glyph"><AppIcon :name="item.icon" /></span>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button type="button" class="nav-item muted-nav support-link">
          <span class="nav-glyph"><AppIcon name="help" /></span>
          <span>Support</span>
        </button>
        <div class="user-mini">
          <div class="avatar" :class="{ admin: isAdmin }" aria-hidden="true">
            <AppIcon :name="isAdmin ? 'verified' : 'user'" />
          </div>
          <div>
            <strong>{{ userRoleLabel }}</strong>
            <span>{{ userEmail }}</span>
          </div>
          <button type="button" class="logout-button" aria-label="Logout" @click="signOut">
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
            <input v-model="fileSearchTerm" type="search" placeholder="Search files..." />
          </label>
          <div class="file-topbar-meta">
            <strong>File Workspace</strong>
            <span class="topbar-divider"></span>
            <button
              type="button"
              class="topbar-icon-button"
              aria-label="Refresh files"
              :disabled="isWorkspaceBusy || blocksWorkspaceMutation"
              @click="refreshFiles"
            >
              <AppIcon name="refresh" />
            </button>
            <button
              type="button"
              class="topbar-icon-button"
              aria-label="Notifications"
              @click="showNotificationsNotice"
            >
              <AppIcon name="notifications" />
            </button>
            <div class="topbar-avatar" :class="{ admin: isAdmin }" aria-hidden="true">
              <AppIcon :name="isAdmin ? 'verified' : 'user'" />
            </div>
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
              <input
                v-model="documentSearchTerm"
                type="search"
                placeholder="Search documents..."
              />
            </label>
            <button
              v-if="isAdmin"
              type="button"
              class="view-switch"
              @click="setActiveView('files')"
            >
              Manage Files
            </button>
          </div>
        </template>
      </header>

      <div
        v-if="activeView === 'files' && operationFeedback"
        class="floating-toast"
        :class="`tone-${operationFeedback.tone}`"
        role="status"
      >
        {{ operationFeedback.message }}
      </div>
      <div
        v-if="activeView === 'chat' && chatSessionFeedback"
        class="floating-toast chat-session-toast"
        :class="`tone-${chatSessionFeedback.tone}`"
        role="status"
      >
        {{ chatSessionFeedback.message }}
      </div>

      <section v-if="activeView === 'files'" class="file-page">
        <div class="file-management-shell">
          <section class="file-sources-pane">
            <FileSourcePanel
              :current-page="normalizedFilePage"
              :disabled="isWorkspaceBusy || blocksWorkspaceMutation"
              :files="paginatedFiles"
              :open-menu-file-id="openFileActionMenuId"
              :page-count="filePageCount"
              :pagination-label="filePaginationLabel"
              :pinned-file-ids="pinnedFileIds"
              :search-term="fileSearchTerm"
              :selected-file-id="selectedFileId"
              :total-file-count="filteredFiles.length"
              :upload-accept="uploadAcceptValue"
              :upload-help-text="uploadHelpText"
              :visible-pages="visibleFilePages"
              @delete-file="requestDeleteFile"
              @rename-file="renameFilePrompt"
              @select-file="chooseFile"
              @set-page="setFilePage"
              @step-page="stepFilePage"
              @toggle-menu="toggleFileActionMenu"
              @toggle-pin="toggleFilePin"
              @toggle-visibility="toggleFileVisibility"
              @upload-selected="handleUploadFileSelected"
            />
          </section>

          <FileInsightPane
            :active-tab="activeFileInsightTab"
            :fullscreen="isFileInsightFullscreen"
            :can-download-preview="Boolean(preview)"
            @change-tab="setFileInsightTab"
            @download-preview="exportPreviewCsv"
            @toggle-fullscreen="toggleFileInsightFullscreen"
          >
            <template #summary>
              <FileSummaryPanel
                :model-stages="modelStageDrafts"
                :providers="availableLlmProviders"
                :model-preference-feedback="modelPreferenceFeedback"
                :model-preference-feedback-kind="modelPreferenceFeedbackKind"
                :can-save-model-preference="canSaveModelPreference"
                :is-model-preference-saving="isModelPreferenceSaving"
                :summary="documentSummary"
                :is-summary-generating="isSummaryLoading"
                :is-summary-saving="isSummarySaving"
                :can-generate-summary="Boolean(selectedVersionId)"
                @provider-change="updateModelStageProvider"
                @model-change="updateModelStageModel"
                @save-model-preference="saveModelPreferenceDefaults"
                @generate-summary="generateSummaryForSelectedVersion"
                @save-summary="saveDocumentSummary"
              />
            </template>

            <template #preview>
              <FilePreviewPanel
                :versions="versions"
                :selected-version-id="selectedVersionId"
                :sheets="sheets"
                :selected-sheet-id="selectedSheetId"
                :selected-sheet="selectedSheet"
                :disabled="blocksWorkspaceMutation"
                :sheet-search-term="sheetSearchTerm"
                :is-sheet-search-loading="isSheetSearchLoading"
                :workbook-row-count="workbookRowCount"
                :preview-range-label="previewRangeLabel"
                :row-lookup="rowLookup"
                :sheet-search-summary="sheetSearchSummary"
                :sheet-search-results="sheetSearchResults"
                :sheet-search-total="sheetSearchTotal"
                :sheet-search-error="sheetSearchError"
                :is-lookup-loading="isLookupLoading"
                :preview="preview"
                :preview-headers="previewHeaders"
                :preview-limit="previewLimit"
                :can-preview-previous="canPreviewPrevious"
                :can-preview-next="canPreviewNext"
                :row-is-highlighted="rowIsHighlighted"
                :is-sheet-search-matched-cell="isSheetSearchMatchedCell"
                @version-change="handlePreviewVersionChange"
                @sheet-change="handlePreviewSheetChange"
                @sheet-search-term-change="setSheetSearchTerm"
                @submit-sheet-search="submitSheetSearch"
                @select-search-match="focusSheetSearchMatch"
                @lookup-row="lookupVisibleRow"
                @load-preview-offset="loadPreviewPage"
                @select-sheet="selectInsightSheet"
              />
            </template>

            <template #schema>
              <FileSchemaPanel
                :selected-file="selectedFile"
                :selected-version="selectedVersion"
                :selected-version-id="selectedVersionId"
                :sheets="sheets"
                :selected-sheet-id="selectedSheetId"
                :selected-sheet="selectedSheet"
                :workbook-row-count="workbookRowCount"
                :schema-columns="schemaColumns"
                :disabled="blocksWorkspaceMutation"
                @select-sheet="selectInsightSheet"
              />
            </template>
          </FileInsightPane>
        </div>
      </section>

      <section
        v-show="activeView === 'chat'"
        class="analysis-page"
        :class="chatWorkspaceClasses"
        :style="chatWorkspaceStyle"
      >
        <aside
          class="chat-session-rail excelai-side-nav"
          :class="{ 'member-session-rail': !isAdmin }"
        >
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
              <span class="session-empty-icon">
                <AppIcon name="chat_bubble" />
              </span>
              <strong>No chat sessions yet</strong>
              <span>Start a new chat to keep your analysis history here.</span>
            </div>
          </div>

          <p v-if="chatSessionError" class="error-note session-error tone-error">
            {{ chatSessionError }}
          </p>

          <div v-if="isAdmin" class="rail-system-links">
            <button type="button" @click="setActiveView('files')">
              <AppIcon name="folder_open" />
              <span>Files</span>
            </button>
          </div>

          <div class="chat-rail-user">
            <div class="avatar" :class="{ admin: isAdmin }" aria-hidden="true">
              <AppIcon :name="isAdmin ? 'verified' : 'user'" />
            </div>
            <div>
              <strong>{{ userEmail }}</strong>
              <span>{{ userRoleLabel }}</span>
            </div>
            <button type="button" class="logout-button" aria-label="Logout" @click="signOut">
              <AppIcon name="logout" />
            </button>
          </div>
        </aside>

        <section class="sheet-stage">
          <div class="workbook-title-bar" aria-label="Current document">
            <span class="workbook-title-icon">
              <AppIcon name="description" />
            </span>
            <div class="workbook-title-copy">
              <span>Current Document</span>
              <strong :title="selectedFileDisplayName">{{ selectedFileDisplayName }}</strong>
            </div>
            <span class="workbook-title-meta">{{ workbookStatusLabel }}</span>
          </div>

          <header class="sheet-topbar">
            <form class="sheet-search-field" @submit.prevent="submitSheetSearch">
              <span class="sheet-search-icon" aria-hidden="true">
                <AppIcon name="search" />
              </span>
              <input
                v-model="sheetSearchTerm"
                type="search"
                placeholder="Search data..."
                :disabled="!selectedVersionId || blocksWorkspaceMutation"
              />
              <button
                v-if="sheetSearchTerm || sheetSearchResults.length > 0 || sheetSearchError"
                type="button"
                class="sheet-search-clear"
                aria-label="Clear sheet search"
                @click="clearSheetSearch"
              >
                <AppIcon name="close" />
              </button>
            </form>
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

          <SheetSearchResults
            v-if="sheetSearchSummary || sheetSearchResults.length > 0"
            :summary="sheetSearchSummary"
            :matches="sheetSearchResults"
            :total-matches="sheetSearchTotal"
            :active-row-id="rowLookup?.mapping.row_id ?? ''"
            :has-error="Boolean(sheetSearchError)"
            :disabled="isLookupLoading || blocksWorkspaceMutation"
            @select="focusSheetSearchMatch"
          />

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
                    'search-match': isSheetSearchMatchedCell(row, columnIndex),
                  }"
                  @click="selectGridCell(row, rowIndex, columnIndex)"
                >
                  <span
                    class="excel-grid-cell-value"
                    :title="getGridCellValue(row, columnIndex)"
                  >
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
              :disabled="blocksWorkspaceMutation"
              @click="runWorkspaceAction((requestId) => selectSheet(sheet, requestId))"
            >
              {{ sheet.sheet_name }}
            </button>
          </div>
        </section>

        <button
          v-if="isChatPanelCollapsed"
          type="button"
          class="chat-panel-expand-button"
          aria-label="Expand chat panel"
          title="Expand chat panel"
          @click="expandChatPanel"
        >
          <AppIcon name="chat_bubble" />
        </button>

        <aside
          class="assistant-column"
          :class="{ resizing: isChatResizing, collapsed: isChatPanelCollapsed }"
          :aria-hidden="isChatPanelCollapsed ? 'true' : undefined"
        >
          <button
            type="button"
            class="chat-column-resizer"
            aria-label="Resize chat panel"
            :tabindex="isChatPanelCollapsed ? -1 : 0"
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
            :answer-supports-deep-thinking="answerSupportsDeepThinking"
            :document-titles="documentTitleMap"
            :active-document="activeDocumentForChat"
            @answer-received="handleChatAnswer"
            @asking-state-changed="handleChatAskingStateChanged"
            @select-citation="handleCitationSelected"
            @select-document="openReferencedDocument"
            @session-created="handleChatSessionCreated"
            @session-title-suggested="handleChatSessionTitleSuggested"
            @collapse="collapseChatPanel"
          />
        </aside>
      </section>
    </section>

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
              ? `Delete "${confirmDialog.file.display_name}" from file management? Active chats keep their existing context.`
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

    <WorkbookUploadDialog
      v-if="uploadDialog"
      :dialog="uploadDialog"
      :error-message="dialogError"
      :is-busy="isWorkspaceBusy || isUploadTaskPending"
      :task="uploadTask"
      @cancel="cancelUploadDialog"
      @confirm="confirmUploadDialog"
    />
  </main>
</template>
