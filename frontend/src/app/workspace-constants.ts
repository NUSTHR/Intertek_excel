import type { PrimaryNavItem } from './workspace-types'

export const previewLimit = 250
export const sheetSearchLimit = 50
export const filePageSize = 6
export const fallbackAllowedUploadExtensions = ['.xls', '.xlsx', '.xlsm', '.xltx', '.xltm']
export const pinnedFileStorageKey = 'excelai-pinned-file-ids'
export const fallbackMaxUploadBytes = 50 * 1024 * 1024
export const minChatColumnWidth = 360
export const maxChatColumnWidth = 560
export const defaultExcelCellWidth = 120
export const defaultExcelRowHeight = 42
export const minExcelCellWidth = 92
export const maxExcelCellWidth = 260
export const minExcelRowHeight = 30
export const maxExcelRowHeight = 86

export const primaryNavItems: PrimaryNavItem[] = [
  { id: 'chat', label: 'Chat', icon: 'chat_bubble' },
  { id: 'files', label: 'Files', icon: 'folder_open' },
  { id: 'settings', label: 'Settings', icon: 'settings', disabled: true },
]
