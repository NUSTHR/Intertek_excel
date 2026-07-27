import type { ChatSession } from '../types/chat'
import type { ExcelFile } from '../types/excel-assets'

export type ActiveView = 'files' | 'chat' | 'pdf' | 'pdf-diagnostics'
export type FileInsightTab = 'summary' | 'preview' | 'schema'
export type ModelStage = 'summary' | 'router' | 'answer'
export type PrimaryNavKey = ActiveView | 'settings'

export type RenameDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }

export type ConfirmDialog =
  | { kind: 'file'; file: ExcelFile }
  | { kind: 'session'; session: ChatSession }

export type UploadDialog =
  | { kind: 'new'; file: File }
  | { kind: 'replace'; file: File }

export type FeedbackTone = 'info' | 'success' | 'warning' | 'error'

export interface SelectSheetOptions {
  preserveSheetSearch?: boolean
}

export interface FeedbackMessage {
  tone: FeedbackTone
  message: string
}

export interface SelectedCell {
  rowKey: string
  rowNumber: number
  columnIndex: number
  address: string
  value: string
}

export interface PrimaryNavItem {
  key: PrimaryNavKey
  label: string
  icon: string
  disabled?: boolean
}
