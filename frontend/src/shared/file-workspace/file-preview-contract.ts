import type { FileDomain } from './file-card-contract'

export interface FilePreviewBlock {
  id: string
  title: string
  content: string
  pageLabel?: string
}

export interface FilePreviewMetrics {
  sheets?: number
  rows?: number
  visible?: number
  highlighted?: number
}

export interface FileVersionOption {
  id: string
  label: string
  status: string
}

export interface FileSheetOption {
  id: string
  name: string
  rowCount: number
  isActive: boolean
}

export interface PreviewHighlightRule {
  rowKey: string
  matchedColumnIndexes: number[]
}

export type PreviewLayout = 'table' | 'block-list'

export interface BaseFilePreviewPanelProps {
  domain: FileDomain
  layout: PreviewLayout
  blocks: FilePreviewBlock[]
  metrics: FilePreviewMetrics
  rangeLabel: string
  canPrevious: boolean
  canNext: boolean
  selectedVersionId: string
  versions: FileVersionOption[]
  selectedSheetId: string
  sheets: FileSheetOption[]
  isLoading: boolean
  searchTerm: string
  searchSummary: string
  searchError: string
  isSearchLoading: boolean
  highlights: PreviewHighlightRule[]
  previewLimit: number
}

export interface BaseFilePreviewPanelEmits {
  versionChange: [versionId: string]
  sheetChange: [sheetId: string]
  searchTermChange: [value: string]
  submitSearch: []
  previousPage: []
  nextPage: []
  selectRow: [rowKey: string]
}
