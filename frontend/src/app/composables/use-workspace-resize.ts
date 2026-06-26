import { ref, type Ref } from 'vue'

import {
  defaultExcelCellWidth,
  defaultExcelRowHeight,
  maxChatColumnWidth,
  maxExcelCellWidth,
  maxExcelRowHeight,
  minChatColumnWidth,
  minExcelCellWidth,
  minExcelRowHeight,
} from '../workspace-constants'
import { clamp } from '../workspace-utils'
import type { SheetPreviewResponse } from '../../types/excel-assets'

interface WorkspaceResizeOptions {
  selectedSheetId: Ref<string>
  preview: Ref<SheetPreviewResponse | null>
  excelDisplayRows: Ref<string[][]>
}

export function useWorkspaceResize(options: WorkspaceResizeOptions) {
  const excelColumnWidths = ref<Record<string, number>>({})
  const excelRowHeights = ref<Record<string, number>>({})
  const chatColumnWidth = ref<number>(420)
  const isChatResizing = ref<boolean>(false)
  const isExcelColumnResizing = ref<boolean>(false)
  const isExcelRowResizing = ref<boolean>(false)
  let excelResizeStartX = 0
  let excelResizeStartY = 0
  let excelResizeStartWidth = 0
  let excelResizeStartHeight = 0
  let excelResizeTargetColumnKey = ''
  let excelResizeTargetRowKey = ''

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
    return `${options.selectedSheetId.value || 'sheet'}:C${columnIndex}`
  }

  function excelRowKey(row: string[], rowIndex: number): string {
    const rowNumber = (options.preview.value?.offset ?? 0) + rowIndex + 1
    return `${options.selectedSheetId.value || 'sheet'}:${row[0] || `R${rowNumber}`}`
  }

  function fillerExcelRowKey(fillerIndex: number): string {
    return `${options.selectedSheetId.value || 'sheet'}:F${fillerRowNumber(fillerIndex)}`
  }

  function fillerRowNumber(fillerIndex: number): number {
    return (options.preview.value?.offset ?? 0) + options.excelDisplayRows.value.length + fillerIndex + 1
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

  return {
    chatColumnWidth,
    isChatResizing,
    isExcelColumnResizing,
    isExcelRowResizing,
    startChatResize,
    stopChatResize,
    excelColumnKey,
    excelRowKey,
    fillerExcelRowKey,
    fillerRowNumber,
    getExcelColumnWidth,
    getExcelRowStyle,
    getFillerExcelRowStyle,
    startExcelColumnResize,
    startExcelColumnResizeFromHeader,
    stopExcelColumnResize,
    startExcelRowResize,
    stopExcelRowResize,
  }
}
