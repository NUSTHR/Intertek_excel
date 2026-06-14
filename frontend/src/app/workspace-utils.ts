import type { ExcelFile } from '../types/excel-assets'

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function rowDomId(rowId: string): string {
  return `excel-row-${rowId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

export function isAllowedUploadFile(file: File, allowedExtensions: string[]): boolean {
  const name = file.name.toLowerCase()
  return allowedExtensions.some((extension) => name.endsWith(extension.toLowerCase()))
}

export function buildUploadAcceptValue(allowedExtensions: string[]): string {
  return allowedExtensions.map((extension) => extension.toLowerCase()).join(',')
}

export function formatSupportedExtensions(allowedExtensions: string[]): string {
  return allowedExtensions.map((extension) => extension.toLowerCase()).join(', ')
}

export function formatBytes(value: number): string {
  if (value <= 0) {
    return '0B'
  }
  const units = ['B', 'KB', 'MB', 'GB']
  const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const scaledValue = value / 1024 ** unitIndex
  const displayValue = scaledValue >= 10 || Number.isInteger(scaledValue)
    ? Math.round(scaledValue).toString()
    : scaledValue.toFixed(1)
  return `${displayValue}${units[unitIndex]}`
}

export function fileTypeLabel(file: ExcelFile): string {
  const extension = file.display_name.split('.').pop()?.toLowerCase()
  if (!extension) {
    return 'Excel'
  }
  return extension.includes('xls') ? 'Excel' : extension.toUpperCase()
}

export function fileIcon(file: ExcelFile): string {
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

export function formatDate(value: string | null | undefined): string {
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

export function shortId(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

export function columnLabel(index: number): string {
  let value = index
  let label = ''
  while (value > 0) {
    const remainder = (value - 1) % 26
    label = String.fromCharCode(65 + remainder) + label
    value = Math.floor((value - 1) / 26)
  }
  return label
}

export function csvEscape(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

export function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (error.message === 'internal server error') {
      return 'Something went wrong on the server. Please try again.'
    }
    return error.message
  }
  return 'Unexpected error.'
}
