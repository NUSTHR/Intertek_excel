import { computed, onBeforeUnmount, ref, watch } from 'vue'

import {
  createPdfUploadTask,
  listPdfKnowledgeFiles,
  listPdfUploadTasks,
} from '../../../api/pdf-knowledge-api'
import type { PdfManagedFile, PdfUploadTask } from '../types'

const pdfFilePageSize = 6
const taskPollIntervalMs = 1100

export function usePdfKnowledgeLibrary() {
  const files = ref<PdfManagedFile[]>([])
  const uploadTasks = ref<PdfUploadTask[]>([])
  const selectedFileId = ref<string>('')
  const searchTerm = ref<string>('')
  const filePage = ref<number>(1)
  const isLoading = ref<boolean>(false)
  const isUploading = ref<boolean>(false)
  const errorMessage = ref<string>('')
  let taskPollTimer: number | null = null

  const filteredFiles = computed(() => {
    const query = searchTerm.value.trim().toLowerCase()
    const visibleFiles = query
      ? files.value.filter((file) => file.name.toLowerCase().includes(query))
      : files.value
    return sortFilesForDisplay(visibleFiles)
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

  const activeTaskCount = computed(() => {
    return uploadTasks.value.filter((task) => task.status !== 'ready' && task.status !== 'failed').length
  })

  const uploadTaskSummary = computed(() => {
    if (activeTaskCount.value === 0) {
      return ''
    }
    return `${activeTaskCount.value} active task${activeTaskCount.value === 1 ? '' : 's'}`
  })

  watch(filteredFiles, (nextFiles) => {
    if (nextFiles.length === 0) {
      return
    }
    if (!nextFiles.some((file) => file.id === selectedFileId.value)) {
      selectedFileId.value = nextFiles[0].id
    }
  })

  async function loadLibrary(): Promise<void> {
    isLoading.value = true
    errorMessage.value = ''
    try {
      const [nextFiles, nextTasks] = await Promise.all([
        listPdfKnowledgeFiles(),
        listPdfUploadTasks(),
      ])
      files.value = nextFiles
      uploadTasks.value = nextTasks
      selectedFileId.value =
        selectedFileId.value || nextFiles.find((file) => file.active)?.id || nextFiles[0]?.id || ''
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    } finally {
      isLoading.value = false
    }
  }

  async function uploadFiles(nextFiles: File[]): Promise<void> {
    if (nextFiles.length === 0) {
      return
    }
    isUploading.value = true
    errorMessage.value = ''
    try {
      const tasks = await createPdfUploadTask(nextFiles)
      uploadTasks.value = [...tasks, ...uploadTasks.value]
      await refreshFilesAndTasks()
      selectedFileId.value = tasks[0]?.fileId ?? selectedFileId.value
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    } finally {
      isUploading.value = false
    }
  }

  function selectFile(file: PdfManagedFile): void {
    selectedFileId.value = file.id
  }

  function setSearchTerm(value: string): void {
    searchTerm.value = value
    filePage.value = 1
  }

  function setFilePage(page: number): void {
    filePage.value = clamp(page, 1, filePageCount.value)
  }

  function stepFilePage(direction: -1 | 1): void {
    setFilePage(normalizedFilePage.value + direction)
  }

  async function refreshFilesAndTasks(): Promise<void> {
    const [nextFiles, nextTasks] = await Promise.all([
      listPdfKnowledgeFiles(),
      listPdfUploadTasks(),
    ])
    files.value = nextFiles
    uploadTasks.value = nextTasks
  }

  function startTaskPollingIfNeeded(): void {
    stopTaskPolling()
    if (uploadTasks.value.every((task) => task.status === 'ready' || task.status === 'failed')) {
      return
    }
    taskPollTimer = window.setTimeout(() => {
      void pollTasks()
    }, taskPollIntervalMs)
  }

  async function pollTasks(): Promise<void> {
    try {
      await refreshFilesAndTasks()
      startTaskPollingIfNeeded()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  function stopTaskPolling(): void {
    if (taskPollTimer !== null) {
      window.clearTimeout(taskPollTimer)
      taskPollTimer = null
    }
  }

  onBeforeUnmount(() => {
    stopTaskPolling()
  })

  return {
    files,
    uploadTasks,
    selectedFileId,
    selectedFile,
    searchTerm,
    filePage,
    filteredFiles,
    paginatedFiles,
    filePageCount,
    normalizedFilePage,
    visibleFilePages,
    activeTaskCount,
    uploadTaskSummary,
    isLoading,
    isUploading,
    errorMessage,
    loadLibrary,
    uploadFiles,
    selectFile,
    setSearchTerm,
    setFilePage,
    stepFilePage,
  }
}

function sortFilesForDisplay(files: PdfManagedFile[]): PdfManagedFile[] {
  const statusWeight: Record<PdfManagedFile['status'], number> = {
    uploading: 0,
    queued: 1,
    parsing: 2,
    indexing: 3,
    failed: 4,
    ready: 5,
    indexed: 6,
  }
  return [...files].sort((left, right) => {
    const statusDelta = statusWeight[left.status] - statusWeight[right.status]
    if (statusDelta !== 0) {
      return statusDelta
    }
    return left.name.localeCompare(right.name)
  })
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF knowledge operation failed.'
}
