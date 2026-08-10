export interface SchemaOverviewBlock {
  fileName: string
  versionLabel: string
  metrics: Array<{ label: string; value: string }>
}

export interface SchemaSheetOption {
  id: string
  name: string
  rowCount: number
  isActive: boolean
}

export interface SchemaColumnBlock {
  id: string
  label: string
  sourceName: string
  type: string
  sample: string
}

export interface BaseFileSchemaPanelProps {
  overview: SchemaOverviewBlock
  sheets: SchemaSheetOption[]
  selectedSheetId: string
  columns: SchemaColumnBlock[]
  isLoading: boolean
  isSwitching: boolean
}

export interface BaseFileSchemaPanelEmits {
  selectSheet: [sheetId: string]
}
