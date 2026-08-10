import { computed, ref, watch } from 'vue'

import {
  cancelPdfUploadBatch,
  cancelPdfUploadTask,
  createPdfUploadTask,
  deletePdfFile,
  listPdfKnowledgeFiles,
  listPdfUploadBatches,
  listPdfUploadTasks,
  renamePdfFile,
  retryPdfUploadBatch,
  retryPdfUploadTask,
  setPdfFileVisibility,
} from '../../../api/pdf-knowledge-api'
import type { PdfBreadcrumbItem, PdfManagedFile, PdfUploadBatch, PdfUploadTask } from '../types'
import { sortPdfFilesByNewest } from '../utils/pdf-file-order'
import { usePdfTaskPolling } from './use-pdf-task-polling'
import { FILE_WORKSPACE_PAGE_SIZE } from '../../../shared/file-workspace/file-pagination-contract'
import { PDF_FILES_ROOT_LABEL } from '../../file-library/domain-presentation'
import type { FileUploadSelection } from '../../../types/file-upload'

const pdfFilePageSize = FILE_WORKSPACE_PAGE_SIZE

interface PdfKnowledgeLibraryOptions {
  onLibraryChanged?: () => void
}

export function usePdfKnowledgeLibrary(options: PdfKnowledgeLibraryOptions = {}) {
  const taskPolling = usePdfTaskPolling()
  const files = ref<PdfManagedFile[]>([])
  const uploadBatches = ref<PdfUploadBatch[]>([])
  const uploadTasks = ref<PdfUploadTask[]>([])
  const selectedFileId = ref<string>('')
  const selectedFileIds = ref<Set<string>>(new Set())
  const selectedScopeId = ref<string>('')
  const searchTerm = ref<string>('')
  const filePage = ref<number>(1)
  const isLoading = ref<boolean>(false)
  const isUploading = ref<boolean>(false)
  const loadErrorMessage = ref<string>('')
  const errorMessage = ref<string>('')
  let focusedUploadFileId = ''
  let navigationRevision = 0
  let focusedUploadNavigationRevision = 0

  const fileLookup = computed(() => {
    return new Map(files.value.map((file) => [file.id, file]))
  })

  const filteredFiles = computed(() => {
    const query = searchTerm.value.trim().toLowerCase()
    const visibleFiles = query ? filesInSelectedScope() : directChildrenOfSelectedScope()
    if (!query) {
      return sortPdfFilesByNewest(visibleFiles)
    }
    return sortPdfFilesByNewest(
      visibleFiles.filter((file) => file.name.toLowerCase().includes(query)),
    )
  })

  const scopeBreadcrumbs = computed<PdfBreadcrumbItem[]>(() => {
    if (!selectedScopeId.value) {
      return [{ id: '', label: PDF_FILES_ROOT_LABEL, active: true }]
    }

    const path: PdfBreadcrumbItem[] = []
    const visited = new Set<string>()
    let currentFile = fileLookup.value.get(selectedScopeId.value)
    while (currentFile && !visited.has(currentFile.id)) {
      path.unshift({ id: currentFile.id, label: currentFile.name })
      visited.add(currentFile.id)
      currentFile = currentFile.parentId ? fileLookup.value.get(currentFile.parentId) : undefined
    }
    const crumbs = [{ id: '', label: PDF_FILES_ROOT_LABEL }, ...path]
    return crumbs.map((crumb, index) => ({
      ...crumb,
      active: index === crumbs.length - 1,
    }))
  })

  const filePageCount = computed(() => {
    return Math.max(1, Math.ceil(filteredFiles.value.length / pdfFilePageSize))
  })

  const normalizedFilePage = computed(() => {
    return clamp(filePage.value, 1, filePageCount.value)
  })

  const paginatedFiles = computed(() => {
    const start = (normalizedFilePage.value - 1) * pdfFilePageSize
    return filteredFiles.value.slice(start, start + pdfFilePageSize)
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

  const selectedFile = computed(() => {
    return files.value.find((file) => file.id === selectedFileId.value)
  })

  const selectedFiles = computed(() => {
    return Array.from(selectedFileIds.value)
      .map((fileId) => fileLookup.value.get(fileId))
      .filter((file): file is PdfManagedFile => Boolean(file))
  })

  const activeTaskCount = computed(() => {
    return uploadTasks.value.filter((task) => !isTerminalTask(task)).length
  })

  const uploadTaskSummary = computed(() => {
    if (activeTaskCount.value === 0) {
      return ''
    }
    return `${activeTaskCount.value} active task${activeTaskCount.value === 1 ? '' : 's'}`
  })

  watch(filteredFiles, () => {
    syncSelectionWithCurrentView()
  })

  watch(files, () => {
    if (!selectedScopeId.value) {
      return
    }
    const selectedScope = fileLookup.value.get(selectedScopeId.value)
    if (!selectedScope || selectedScope.kind !== 'folder') {
      selectedScopeId.value = ''
      filePage.value = 1
    }
  })

  async function loadLibrary(): Promise<void> {
    isLoading.value = true
    loadErrorMessage.value = ''
    errorMessage.value = ''
    try {
      await refreshFilesAndTasks()
      if (selectedFileIds.value.size === 0) {
        const initialFile =
          files.value.find((file) => file.active) ??
          files.value.find((file) => file.kind !== 'folder') ??
          files.value[0]
        if (initialFile) {
          setSingleSelection(initialFile)
        }
      }
      syncSelectionWithCurrentView()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      const message = toErrorMessage(error)
      loadErrorMessage.value = message
      errorMessage.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function uploadFiles(selections: FileUploadSelection[]): Promise<void> {
    if (selections.length === 0) {
      return
    }
    const targetScopeId = selectedScopeId.value
    isUploading.value = true
    errorMessage.value = ''
    try {
      const result = await createPdfUploadTask(selections, targetScopeId || undefined)
      if (result.batch) {
        uploadBatches.value = [result.batch, ...uploadBatches.value]
      }
      uploadTasks.value = [...result.tasks, ...uploadTasks.value]
      await refreshFilesAndTasks()
      if (result.tasks[0]?.fileId) {
        focusedUploadFileId = result.tasks[0].fileId
        focusedUploadNavigationRevision = navigationRevision
        revealFocusedUpload(true)
      }
      options.onLibraryChanged?.()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    } finally {
      isUploading.value = false
    }
  }

  function selectFile(file: PdfManagedFile): void {
    markUserNavigation()
    const fileScopeId = scopeIdForFile(file)
    if (fileScopeId !== selectedScopeId.value) {
      selectedScopeId.value = fileScopeId
      filePage.value = 1
      setSingleSelection(file)
      return
    }
    toggleSelection(file)
  }

  function openScope(scopeId: string): void {
    selectScope(scopeId)
  }

  function selectScope(scopeId: string): void {
    markUserNavigation()
    const normalizedScopeId = scopeId || ''
    if (normalizedScopeId) {
      const nextScope = fileLookup.value.get(normalizedScopeId)
      if (!nextScope) {
        return
      }
      if (nextScope.kind !== 'folder') {
        selectFile(nextScope)
        return
      }
    }
    selectedScopeId.value = normalizedScopeId
    filePage.value = 1
    clearSelection()
  }

  function setSearchTerm(value: string): void {
    markUserNavigation()
    searchTerm.value = value
    filePage.value = 1
  }

  function setFilePage(page: number): void {
    markUserNavigation()
    filePage.value = clamp(page, 1, filePageCount.value)
  }

  function stepFilePage(direction: -1 | 1): void {
    setFilePage(normalizedFilePage.value + direction)
  }

  async function refreshFilesAndTasks(): Promise<boolean> {
    const [filesResult, batchesResult, tasksResult] = await Promise.allSettled([
      listPdfKnowledgeFiles(),
      listPdfUploadBatches(),
      listPdfUploadTasks(),
    ])
    if (filesResult.status === 'rejected') {
      throw filesResult.reason
    }
    files.value = filesResult.value
    if (batchesResult.status === 'fulfilled') {
      uploadBatches.value = batchesResult.value
    }
    if (tasksResult.status === 'fulfilled') {
      uploadTasks.value = tasksResult.value
    }
    const activityErrors = [
      batchesResult.status === 'rejected' ? batchesResult.reason : undefined,
      tasksResult.status === 'rejected' ? tasksResult.reason : undefined,
    ].filter((error): error is unknown => error !== undefined)
    if (activityErrors.length > 0) {
      errorMessage.value = `PDF files loaded, but upload activity is unavailable: ${toErrorMessage(activityErrors[0])}`
    }
    syncSelectionWithCurrentView()
    revealFocusedUpload()
    return tasksResult.status === 'fulfilled'
  }

  function startTaskPollingIfNeeded(): void {
    taskPolling.stopPolling()
    if (uploadTasks.value.every(isTerminalTask)) {
      return
    }
    taskPolling.startPolling({
      load: async () => {
        const tasksAreFresh = await refreshFilesAndTasks()
        if (!tasksAreFresh) {
          throw new Error('PDF upload task status is temporarily unavailable.')
        }
        return uploadTasks.value
      },
      isTerminal: (tasks) => tasks.every(isTerminalTask),
      onTerminal: () => {
        options.onLibraryChanged?.()
      },
      onError: (error, isFinalAttempt) => {
        if (isFinalAttempt) {
          errorMessage.value = toErrorMessage(error)
        }
      },
    })
  }

  async function cancelTask(taskId: string): Promise<void> {
    errorMessage.value = ''
    try {
      await cancelPdfUploadTask(taskId)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function retryTask(taskId: string): Promise<void> {
    errorMessage.value = ''
    try {
      await retryPdfUploadTask(taskId)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function cancelBatch(batchId: string): Promise<void> {
    errorMessage.value = ''
    try {
      await cancelPdfUploadBatch(batchId)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function retryBatch(batchId: string): Promise<void> {
    errorMessage.value = ''
    try {
      await retryPdfUploadBatch(batchId)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function renameFile(file: PdfManagedFile, displayName: string): Promise<void> {
    const normalizedName = displayName.trim()
    if (!normalizedName || normalizedName === file.name) {
      return
    }
    errorMessage.value = ''
    try {
      await renamePdfFile(file.id, normalizedName)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function toggleFileVisibility(file: PdfManagedFile): Promise<void> {
    errorMessage.value = ''
    try {
      await setPdfFileVisibility(file.id, !file.visibleToMembers)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function deleteFile(file: PdfManagedFile, confirmDelete = false): Promise<boolean> {
    errorMessage.value = ''
    try {
      await deletePdfFile(file.id, confirmDelete)
      await refreshFilesAndTasks()
      options.onLibraryChanged?.()
      if (selectedFileIds.value.has(file.id)) {
        const nextSelection = new Set(selectedFileIds.value)
        nextSelection.delete(file.id)
        selectedFileIds.value = nextSelection
        selectedFileId.value = firstSelectedId(nextSelection)
      }
      return true
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
      return false
    }
  }

  function directChildrenOfSelectedScope(): PdfManagedFile[] {
    return files.value.filter((file) => (file.parentId ?? '') === selectedScopeId.value)
  }

  function filesInSelectedScope(): PdfManagedFile[] {
    if (!selectedScopeId.value) {
      return files.value
    }
    return files.value.filter((file) =>
      file.id !== selectedScopeId.value &&
      isDescendantOrSelf(file.id, selectedScopeId.value, fileLookup.value),
    )
  }

  function syncSelectionWithCurrentView(): void {
    if (selectedScopeId.value) {
      const selectedScope = fileLookup.value.get(selectedScopeId.value)
      if (!selectedScope || selectedScope.kind !== 'folder') {
        selectedScopeId.value = ''
      }
    }

    const currentFiles = filteredFiles.value
    if (currentFiles.length === 0) {
      selectedFileId.value = ''
      selectedFileIds.value = new Set()
      return
    }
    const currentIds = new Set(currentFiles.map((file) => file.id))
    const nextSelection = new Set(
      Array.from(selectedFileIds.value).filter((fileId) => currentIds.has(fileId)),
    )
    if (nextSelection.size !== selectedFileIds.value.size) {
      selectedFileIds.value = nextSelection
    }
    if (!selectedFileId.value || !currentIds.has(selectedFileId.value)) {
      selectedFileId.value = firstSelectedId(nextSelection)
    }
  }

  function scopeIdForFile(file: PdfManagedFile): string {
    const parentFile = file.parentId ? fileLookup.value.get(file.parentId) : undefined
    return parentFile?.kind === 'folder' ? parentFile.id : ''
  }

  function toggleSelection(file: PdfManagedFile): void {
    const nextSelection = new Set(selectedFileIds.value)
    if (nextSelection.has(file.id)) {
      nextSelection.delete(file.id)
      selectedFileIds.value = nextSelection
      selectedFileId.value = firstSelectedId(nextSelection)
      return
    }
    nextSelection.add(file.id)
    selectedFileIds.value = nextSelection
    selectedFileId.value = file.id
  }

  function setSingleSelection(file: PdfManagedFile): void {
    selectedScopeId.value = scopeIdForFile(file)
    selectedFileIds.value = new Set([file.id])
    selectedFileId.value = file.id
  }

  function setSingleSelectionById(fileId: string): void {
    const file = fileLookup.value.get(fileId)
    if (!file) {
      return
    }
    searchTerm.value = ''
    setSingleSelection(file)
    const fileIndex = filteredFiles.value.findIndex((candidate) => candidate.id === file.id)
    filePage.value =
      fileIndex >= 0 ? Math.floor(fileIndex / pdfFilePageSize) + 1 : 1
  }

  function focusFileById(fileId: string): boolean {
    if (!fileLookup.value.has(fileId)) {
      return false
    }
    setSingleSelectionById(fileId)
    return true
  }

  function revealFocusedUpload(force = false): void {
    if (!focusedUploadFileId) {
      return
    }
    if (!force && focusedUploadNavigationRevision !== navigationRevision) {
      focusedUploadFileId = ''
      return
    }
    if (
      !force &&
      selectedFileId.value &&
      selectedFileId.value !== focusedUploadFileId
    ) {
      focusedUploadFileId = ''
      return
    }
    setSingleSelectionById(focusedUploadFileId)
    const task = uploadTasks.value.find(
      (candidate) => candidate.fileId === focusedUploadFileId,
    )
    if (task && isTerminalTask(task)) {
      focusedUploadFileId = ''
    }
  }

  function clearSelection(): void {
    selectedFileIds.value = new Set()
    selectedFileId.value = ''
  }

  function markUserNavigation(): void {
    navigationRevision += 1
    if (focusedUploadFileId) {
      focusedUploadFileId = ''
    }
  }

  return {
    files,
    uploadBatches,
    uploadTasks,
    selectedFileId,
    selectedFileIds,
    selectedScopeId,
    selectedFile,
    selectedFiles,
    searchTerm,
    filePage,
    filteredFiles,
    paginatedFiles,
    scopeBreadcrumbs,
    filePageCount,
    normalizedFilePage,
    visibleFilePages,
    activeTaskCount,
    uploadTaskSummary,
    isLoading,
    isUploading,
    loadErrorMessage,
    errorMessage,
    loadLibrary,
    uploadFiles,
    cancelTask,
    retryTask,
    cancelBatch,
    retryBatch,
    renameFile,
    toggleFileVisibility,
    deleteFile,
    focusFileById,
    selectFile,
    selectScope,
    openScope,
    setSearchTerm,
    setFilePage,
    stepFilePage,
  }
}

function isTerminalTask(task: PdfUploadTask): boolean {
  return task.status === 'ready' || task.status === 'failed' || task.status === 'cancelled'
}

function firstSelectedId(selectedIds: Set<string>): string {
  return selectedIds.values().next().value ?? ''
}

function isDescendantOrSelf(
  fileId: string,
  ancestorId: string,
  fileLookup: Map<string, PdfManagedFile>,
): boolean {
  let currentFile = fileLookup.get(fileId)
  const visited = new Set<string>()
  while (currentFile && !visited.has(currentFile.id)) {
    if (currentFile.id === ancestorId) {
      return true
    }
    visited.add(currentFile.id)
    currentFile = currentFile.parentId ? fileLookup.get(currentFile.parentId) : undefined
  }
  return false
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF knowledge operation failed.'
}
