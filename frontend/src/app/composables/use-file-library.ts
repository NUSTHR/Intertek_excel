import { computed, ref, type Ref } from 'vue'

import { filePageSize, pinnedFileStorageKey } from '../workspace-constants'
import { clamp } from '../workspace-utils'
import type { ExcelFile } from '../../types/excel-assets'

interface FileLibraryOptions {
  files: Ref<ExcelFile[]>
  onInteraction?: () => void
}

export function useFileLibrary(options: FileLibraryOptions) {
  const files = options.files
  const fileSearchTerm = ref<string>('')
  const filePage = ref<number>(1)
  const pinnedFileIds = ref<string[]>(loadPinnedFileIds())

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

  const normalizedFilePage = computed(() => {
    return clamp(filePage.value, 1, filePageCount.value)
  })

  const paginatedFiles = computed(() => {
    const start = (normalizedFilePage.value - 1) * filePageSize
    return filteredFiles.value.slice(start, start + filePageSize)
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

  function setFilePage(page: number): void {
    filePage.value = clamp(page, 1, filePageCount.value)
    options.onInteraction?.()
  }

  function stepFilePage(direction: -1 | 1): void {
    setFilePage(normalizedFilePage.value + direction)
  }

  function isFilePinned(fileId: string): boolean {
    return pinnedFileIds.value.includes(fileId)
  }

  function toggleFilePin(file: ExcelFile): void {
    options.onInteraction?.()
    const nextIds = isFilePinned(file.file_id)
      ? pinnedFileIds.value.filter((fileId) => fileId !== file.file_id)
      : [file.file_id, ...pinnedFileIds.value]
    pinnedFileIds.value = nextIds
    savePinnedFileIds(nextIds)
  }

  function resetFilePage(): void {
    filePage.value = 1
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

  return {
    fileSearchTerm,
    filePage,
    pinnedFileIds,
    filteredFiles,
    filePageCount,
    normalizedFilePage,
    paginatedFiles,
    visibleFilePages,
    filePaginationLabel,
    setFilePage,
    stepFilePage,
    isFilePinned,
    toggleFilePin,
    resetFilePage,
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
