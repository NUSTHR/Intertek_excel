<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

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
import { getCurrentUser, logout as logoutSession } from '../api/auth-api'
import { clearAuthToken, getAuthToken, setAuthToken } from '../api/auth-token'
import {
  generateDocumentSummary,
  getDocumentSummary,
  updateDocumentSummary,
} from '../api/document-summaries-api'
import { getLlmModelOptions, getLlmPreference, saveLlmPreference } from '../api/llm-api'
import AppIcon from '../components/AppIcon.vue'
import AuthPanel from '../components/AuthPanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import DocumentSummaryCard from '../components/DocumentSummaryCard.vue'
import type { AuthResponse, AuthUser } from '../types/auth'
import type { ChatAnswer, ChatSession, ExcelCitation, SelectedDocument } from '../types/chat'
import type { DocumentSummary, DocumentSummaryUpdate } from '../types/document-summary'
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
type PrimaryNavKey = ActiveView | 'settings'
type RenameDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }
type ConfirmDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }
type UploadDialog =
  | { kind: 'new'; file: File }
  | { kind: 'replace'; file: File }
type FeedbackTone = 'info' | 'success' | 'warning' | 'error'

interface FeedbackMessage {
  tone: FeedbackTone
  message: string
}

interface SelectedCell {
  rowKey: string
  rowNumber: number
  columnIndex: number
  address: string
  value: string
}

interface PrimaryNavItem {
  key: PrimaryNavKey
  label: string
  icon: string
  disabled?: boolean
}

const previewLimit = 250
const filePageSize = 6
const allowedUploadExtensions = ['.xls', '.xlsx', '.xlsm', '.xltx', '.xltm']
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
const primaryNavItems: PrimaryNavItem[] = [
  { key: 'chat', label: 'Chat', icon: 'chat_bubble' },
  { key: 'files', label: 'Files', icon: 'folder_open' },
  { key: 'settings', label: 'Settings', icon: 'settings', disabled: true },
]

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
const lookupRowId = ref<string>('')
const operationFeedback = ref<FeedbackMessage | null>(null)
const chatSessionFeedback = ref<FeedbackMessage | null>(null)
const errorMessage = ref<string>('')
const searchTerm = ref<string>('')
const isWorkspaceBusy = ref<boolean>(false)
const isSummaryLoading = ref<boolean>(false)
const isSummarySaving = ref<boolean>(false)
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
const isChatPanelCollapsed = ref<boolean>(false)
const isChatAnswerPending = ref<boolean>(false)
const filePage = ref<number>(1)
let operationFeedbackTimer: number | null = null
let chatSessionFeedbackTimer: number | null = null
let modelPreferenceSaveTimer: number | null = null
let isModelPreferenceReady = false
let isApplyingModelPreference = false
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

const isAdmin = computed(() => currentUser.value?.role === 'admin')

const visiblePrimaryNavItems = computed(() => {
  return primaryNavItems.filter((item) => item.key !== 'files' || isAdmin.value)
})

const userInitial = computed(() => {
  const email = currentUser.value?.email ?? ''
  return email.trim().charAt(0).toUpperCase() || 'U'
})

const userEmail = computed(() => currentUser.value?.email ?? '')

const userRoleLabel = computed(() => (isAdmin.value ? 'Administrator' : 'Workspace user'))

const blocksWorkspaceMutation = computed(() => isChatAnswerPending.value)


onMounted(() => {
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', syncActiveViewFromLocation)
  }
  void restoreAuthentication()
})

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('hashchange', syncActiveViewFromLocation)
  }
  clearOperationFeedback()
  clearChatSessionFeedback()
  clearModelPreferenceSave()
  stopChatResize()
  stopExcelColumnResize()
  stopExcelRowResize()
})

watch(
  () => [
    summaryProvider.value,
    summaryModel.value,
    routerProvider.value,
    routerModel.value,
    answerProvider.value,
    answerModel.value,
  ],
  () => {
    queueModelPreferenceSave()
  },
)

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
  await loadLlmModelOptions()
  await loadChatSessions()
  await refreshFiles()
}

async function restoreAuthentication(): Promise<void> {
  authErrorMessage.value = ''
  isAuthChecking.value = true
  try {
    if (!getAuthToken()) {
      currentUser.value = null
      return
    }
    currentUser.value = await getCurrentUser()
    await initializeWorkspace()
  } catch (error: unknown) {
    clearAuthToken()
    currentUser.value = null
    authErrorMessage.value = toErrorMessage(error)
  } finally {
    isAuthChecking.value = false
  }
}

async function handleAuthenticated(response: AuthResponse): Promise<void> {
  setAuthToken(response.access_token)
  currentUser.value = response.user
  authErrorMessage.value = ''
  await resetWorkspaceState()
  await initializeWorkspace()
}

async function signOut(): Promise<void> {
  try {
    await logoutSession()
  } catch {
    // Local token cleanup is still the source of truth for the browser session.
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
  errorMessage.value = ''
  chatSessionError.value = ''
  isChatAnswerPending.value = false
  closeActionMenus()
}

async function loadLlmModelOptions(): Promise<void> {
  const options = await getLlmModelOptions()
  availableLlmModels.value = options.models
  availableLlmProviders.value = options.providers
  isApplyingModelPreference = true
  try {
    applyModelDefaults(options.defaults)
    try {
      const preference = await getLlmPreference()
      applyModelDefaults(preference)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  } finally {
    await nextTick()
    isApplyingModelPreference = false
    isModelPreferenceReady = true
  }
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
  errorMessage.value = ''
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
      errorMessage.value = toErrorMessage(error)
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
  errorMessage.value = ''
  const requestId = nextWorkspaceSelectionRequestId()
  const busyRequestId = beginWorkspaceBusy()
  try {
    await selectFile(file, requestId)
    if (view) {
      setActiveView(view)
    }
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      errorMessage.value = toErrorMessage(error)
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
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  selectedCell.value = null
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
    return
  }
  selectedVersionId.value = versionId
  selectedSheetId.value = ''
  preview.value = null
  rowLookup.value = null
  documentSummary.value = null
  selectedCell.value = null
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

async function selectCurrentSheet(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  const sheet = sheets.value.find((item) => item.sheet_id === selectedSheetId.value)
  if (sheet) {
    await runWorkspaceAction((requestId) => selectSheet(sheet, requestId))
  }
}

async function selectSheet(
  sheet: ExcelSheet,
  requestId = nextWorkspaceSelectionRequestId(),
): Promise<void> {
  if (!isCurrentWorkspaceSelection(requestId)) {
    return
  }
  selectedSheetId.value = sheet.sheet_id
  rowLookup.value = null
  lookupRowId.value = ''
  selectedCell.value = null
  const nextPreview = await previewExcelSheet(sheet.sheet_id, 0, previewLimit)
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
  errorMessage.value = ''
  try {
    const safeOffset = Math.max(0, offset)
    rowLookup.value = null
    selectedCell.value = null
    const nextPreview = await previewExcelSheet(sheetId, safeOffset, previewLimit)
    if (!isCurrentWorkspaceSelection(requestId) || selectedSheetId.value !== sheetId) {
      return
    }
    preview.value = nextPreview
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      errorMessage.value = toErrorMessage(error)
    }
  }
}

async function generateSummaryForSelectedVersion(): Promise<void> {
  if (!selectedVersionId.value) {
    errorMessage.value = 'Select a version first.'
    return
  }
  const versionId = selectedVersionId.value
  const selectionRequestId = workspaceSelectionRequestId
  const generationRequestId = ++summaryGenerationRequestId
  errorMessage.value = ''
  isSummaryLoading.value = true
  try {
    const nextSummary = await generateDocumentSummary(
      versionId,
      summaryModel.value || null,
      summaryProvider.value || null,
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
      errorMessage.value = toErrorMessage(error)
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
    errorMessage.value = 'Select a version first.'
    onSaved(false)
    return
  }
  const versionId = selectedVersionId.value
  const selectionRequestId = workspaceSelectionRequestId
  const saveRequestId = ++summarySaveRequestId
  errorMessage.value = ''
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
      errorMessage.value = toErrorMessage(error)
    }
    onSaved(false)
  } finally {
    if (saveRequestId === summarySaveRequestId) {
      isSummarySaving.value = false
    }
  }
}

function openUploadDialog(): void {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
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
  if (!isWorkspaceBusy.value && !blocksWorkspaceMutation.value) {
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
  if (isWorkspaceBusy.value || !ensureWorkspaceMutationAllowed()) {
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
    errorMessage.value = 'Only Excel files are supported: .xls, .xlsx, .xlsm, .xltx, .xltm.'
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
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
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
      errorMessage.value = ''
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

  errorMessage.value = ''
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
      `${result.display_name} deleted. Removed ${result.deleted_versions} version(s), ${result.deleted_sheets} sheet(s), ${result.deleted_artifacts} artifact(s), ${result.deleted_summaries} summary record(s), and ${result.deleted_chat_session_documents} chat attachment(s).`,
      5200,
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
    errorMessage.value = 'Choose an Excel workbook first.'
    return
  }

  errorMessage.value = ''
  const requestId = nextWorkspaceSelectionRequestId()
  const busyRequestId = beginWorkspaceBusy()
  try {
    const result = await uploadExcelFile(file, replaceExisting)
    pendingReplaceFile.value = null
    selectedUploadFile.value = null
    uploadDialog.value = null
    dialogError.value = ''
    if (fileInput.value) {
      fileInput.value.value = ''
    }
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
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError && error.requiresConfirmation) {
      pendingReplaceFile.value = file
      selectedUploadFile.value = null
      uploadDialog.value = { kind: 'replace', file }
      dialogError.value = ''
      return
    }
    if (isCurrentWorkspaceSelection(requestId)) {
      if (uploadDialog.value) {
        dialogError.value = toErrorMessage(error)
      } else {
        errorMessage.value = toErrorMessage(error)
      }
    }
  } finally {
    finishWorkspaceBusy(busyRequestId)
  }
}

async function lookupRow(): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  if (!selectedSheetId.value || !lookupRowId.value.trim()) {
    errorMessage.value = 'Enter a row id such as S001_R25.'
    return
  }
  await lookupRowInSheet(selectedSheetId.value, lookupRowId.value.trim())
}

async function lookupVisibleRow(row: string[]): Promise<void> {
  const rowId = row[0]?.trim()
  if (!rowId || isLookupLoading.value || !ensureWorkspaceMutationAllowed()) {
    return
  }
  lookupRowId.value = rowId
  await lookupRow()
}

async function lookupRowInSheet(sheetId: string, rowId: string): Promise<void> {
  const requestId = ++rowLookupRequestId
  const selectionRequestId = workspaceSelectionRequestId
  errorMessage.value = ''
  isLookupLoading.value = true
  try {
    const result = await lookupExcelRow(sheetId, rowId)
    if (!isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      return
    }
    const nextPreview = await previewForLookupRow(result)
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
    if (isCurrentRowLookup(requestId, selectionRequestId, sheetId)) {
      errorMessage.value = toErrorMessage(error)
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
): Promise<SheetPreviewResponse | null> {
  const rowZeroIndex = Math.max(0, result.mapping.raw_csv_row_number - 1)
  const currentOffset = preview.value?.offset ?? 0
  const currentEnd = currentOffset + (preview.value?.rows.length ?? 0)
  const isCurrentSheetPreview = preview.value?.sheet.sheet_id === result.sheet.sheet_id
  if (!isCurrentSheetPreview || rowZeroIndex < currentOffset || rowZeroIndex >= currentEnd) {
    const centeredOffset = Math.max(0, rowZeroIndex - 24)
    return previewExcelSheet(result.sheet.sheet_id, centeredOffset, previewLimit)
  }
  return null
}

async function handleCitationSelected(citation: ExcelCitation): Promise<void> {
  if (!ensureWorkspaceMutationAllowed()) {
    return
  }
  setActiveView('chat')
  errorMessage.value = ''
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
    lookupRowId.value = citation.row_id
    await lookupRowInSheet(citation.sheet_id, citation.row_id)
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      errorMessage.value = toErrorMessage(error)
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
  errorMessage.value = ''
  const busyRequestId = beginWorkspaceBusy()
  try {
    await action(requestId)
  } catch (error: unknown) {
    if (isCurrentWorkspaceSelection(requestId)) {
      errorMessage.value = toErrorMessage(error)
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

function handleModelProviderChange(stage: ModelStage): void {
  ensureStageModel(stage)
  queueModelPreferenceSave()
}

function queueModelPreferenceSave(): void {
  if (!isModelPreferenceReady || isApplyingModelPreference || typeof window === 'undefined') {
    return
  }
  if (!isCompleteModelPreference()) {
    return
  }
  if (modelPreferenceSaveTimer !== null) {
    window.clearTimeout(modelPreferenceSaveTimer)
  }
  modelPreferenceSaveTimer = window.setTimeout(() => {
    modelPreferenceSaveTimer = null
    void persistModelPreference()
  }, 350)
}

async function persistModelPreference(): Promise<void> {
  try {
    await saveLlmPreference({
      summary_provider: summaryProvider.value,
      summary_model: summaryModel.value,
      router_provider: routerProvider.value,
      router_model: routerModel.value,
      answer_provider: answerProvider.value,
      answer_model: answerModel.value,
    })
  } catch (error: unknown) {
    errorMessage.value = toErrorMessage(error)
  }
}

function clearModelPreferenceSave(): void {
  if (modelPreferenceSaveTimer !== null) {
    window.clearTimeout(modelPreferenceSaveTimer)
    modelPreferenceSaveTimer = null
  }
}

function isCompleteModelPreference(): boolean {
  return Boolean(
    summaryProvider.value &&
      summaryModel.value &&
      routerProvider.value &&
      routerModel.value &&
      answerProvider.value &&
      answerModel.value,
  )
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

function showOperationFeedback(
  tone: FeedbackTone,
  message: string,
  durationMs = 3200,
): void {
  operationFeedback.value = { tone, message }
  if (operationFeedbackTimer !== null) {
    window.clearTimeout(operationFeedbackTimer)
  }
  operationFeedbackTimer = window.setTimeout(() => {
    operationFeedback.value = null
    operationFeedbackTimer = null
  }, durationMs)
}

function clearOperationFeedback(): void {
  if (operationFeedbackTimer !== null) {
    window.clearTimeout(operationFeedbackTimer)
    operationFeedbackTimer = null
  }
  operationFeedback.value = null
}

function showChatSessionFeedback(
  tone: FeedbackTone,
  message: string,
  durationMs = 2800,
): void {
  chatSessionFeedback.value = { tone, message }
  if (chatSessionFeedbackTimer !== null) {
    window.clearTimeout(chatSessionFeedbackTimer)
  }
  chatSessionFeedbackTimer = window.setTimeout(() => {
    chatSessionFeedback.value = null
    chatSessionFeedbackTimer = null
  }, durationMs)
}

function clearChatSessionFeedback(): void {
  if (chatSessionFeedbackTimer !== null) {
    window.clearTimeout(chatSessionFeedbackTimer)
    chatSessionFeedbackTimer = null
  }
  chatSessionFeedback.value = null
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === 'internal server error') {
      return 'Something went wrong on the server. Please try again.'
    }
    return error.message
  }
  return 'Unexpected error.'
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
          <div class="avatar">{{ userInitial }}</div>
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
            <input v-model="searchTerm" type="search" placeholder="Search files..." />
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
              <input v-model="searchTerm" type="search" placeholder="Search documents..." />
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

      <div v-if="errorMessage || (activeView === 'files' && operationFeedback)" class="notice-row">
        <p
          v-if="activeView === 'files' && operationFeedback"
          class="status-note"
          :class="`tone-${operationFeedback.tone}`"
        >
          {{ operationFeedback.message }}
        </p>
        <p v-if="errorMessage" class="error-note tone-error">{{ errorMessage }}</p>
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
        <section class="file-list-panel">
          <div class="panel-heading">
            <div>
              <h3>File Sources</h3>
            </div>
            <span class="files-found-label">{{ filteredFiles.length }} Files Found</span>
          </div>

          <button
            type="button"
            class="file-upload-zone"
            :class="{ dragging: isUploadDragging }"
            :disabled="isWorkspaceBusy || blocksWorkspaceMutation"
            @click="openUploadDialog"
            @dragenter.prevent="handleUploadDragEnter"
            @dragover.prevent="handleUploadDragEnter"
            @dragleave.prevent="handleUploadDragLeave"
            @drop.prevent="handleUploadDrop"
          >
            <span class="file-upload-icon">
              <AppIcon name="upload_file" />
            </span>
            <strong>Click or drag files to upload</strong>
            <span>Supports Excel workbooks (Max 50MB)</span>
          </button>

          <div class="file-card-list">
            <article
              v-for="file in paginatedFiles"
              :key="file.file_id"
              role="button"
              tabindex="0"
              class="file-library-card"
              :class="{
                selected: file.file_id === selectedFileId,
                pinned: isFilePinned(file.file_id),
                'menu-open': openFileActionMenuId === file.file_id,
              }"
              :aria-disabled="blocksWorkspaceMutation ? 'true' : undefined"
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
                  :disabled="blocksWorkspaceMutation"
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
                <button
                  type="button"
                  :disabled="blocksWorkspaceMutation"
                  @click="renameFilePrompt(file)"
                >
                  <AppIcon name="edit" />
                  Rename
                </button>
                <button
                  type="button"
                  class="danger-text"
                  :disabled="blocksWorkspaceMutation"
                  @click="requestDeleteFile(file)"
                >
                  <AppIcon name="close" />
                  Delete
                </button>
              </span>
            </article>

            <div v-if="filteredFiles.length === 0" class="file-empty-panel">
              {{ searchTerm.trim() ? 'No matching workbooks.' : 'Upload a workbook to get started.' }}
            </div>
          </div>

          <div class="file-pagination">
            <button
              type="button"
              class="pagination-link"
              :disabled="normalizedFilePage <= 1"
              @click="stepFilePage(-1)"
            >
              <AppIcon name="chevron_left" />
              Previous
            </button>
            <div class="pagination-pages">
              <button
                v-for="pageNumber in visibleFilePages"
                :key="pageNumber"
                type="button"
                :class="{ active: pageNumber === normalizedFilePage }"
                :aria-current="pageNumber === normalizedFilePage ? 'page' : undefined"
                @click="setFilePage(pageNumber)"
              >
                {{ pageNumber }}
              </button>
            </div>
            <span class="pagination-range">{{ filePaginationLabel }}</span>
            <button
              type="button"
              class="pagination-link"
              :disabled="normalizedFilePage >= filePageCount"
              @click="stepFilePage(1)"
            >
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
                      <select v-model="summaryProvider" @change="handleModelProviderChange('summary')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`summary-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="summaryModel" @change="queueModelPreferenceSave">
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
                      <select v-model="routerProvider" @change="handleModelProviderChange('router')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`router-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="routerModel" @change="queueModelPreferenceSave">
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
                      <select v-model="answerProvider" @change="handleModelProviderChange('answer')">
                        <option
                          v-for="provider in availableLlmProviders"
                          :key="`answer-provider-${provider.provider}`"
                          :value="provider.provider"
                        >
                          {{ provider.label }}
                        </option>
                      </select>
                      <select v-model="answerModel" @change="queueModelPreferenceSave">
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

                <DocumentSummaryCard
                  :summary="documentSummary"
                  :is-generating="isSummaryLoading"
                  :is-saving="isSummarySaving"
                  :can-generate="Boolean(selectedVersionId)"
                  @generate="generateSummaryForSelectedVersion"
                  @save="saveDocumentSummary"
                />
              </section>

              <section v-else-if="activeFileInsightTab === 'preview'" class="file-preview-panel">
                <div class="file-preview-controls">
                  <label>
                    <span>Version</span>
                    <select
                      v-model="selectedVersionId"
                      :disabled="versions.length === 0 || blocksWorkspaceMutation"
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
                      :disabled="sheets.length === 0 || blocksWorkspaceMutation"
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
                      <button
                        type="button"
                        :disabled="isLookupLoading || blocksWorkspaceMutation"
                        @click="lookupRow"
                      >
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
                        :disabled="!canPreviewPrevious || blocksWorkspaceMutation"
                        @click="loadPreviewPage((preview?.offset ?? 0) - previewLimit)"
                      >
                        Previous
                      </button>
                      <button
                        type="button"
                        class="secondary-button"
                        :disabled="!canPreviewNext || blocksWorkspaceMutation"
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
                    :disabled="blocksWorkspaceMutation"
                    @click="runWorkspaceAction((requestId) => selectSheet(sheet, requestId))"
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
                      :disabled="blocksWorkspaceMutation"
                      @click="runWorkspaceAction((requestId) => selectSheet(sheet, requestId))"
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

      <section
        v-show="activeView === 'chat'"
        class="analysis-page"
        :class="chatWorkspaceClasses"
        :style="chatWorkspaceStyle"
      >
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

          <p
            v-if="chatSessionFeedback"
            class="status-note session-feedback"
            :class="`tone-${chatSessionFeedback.tone}`"
          >
            {{ chatSessionFeedback.message }}
          </p>
          <p v-if="chatSessionError" class="error-note session-error tone-error">
            {{ chatSessionError }}
          </p>

          <div class="rail-system-links">
            <button v-if="isAdmin" type="button" @click="setActiveView('files')">
              <AppIcon name="folder_open" />
              <span>Files</span>
            </button>
          </div>

          <div class="chat-rail-user">
            <div class="avatar">{{ userInitial }}</div>
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
