import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  fileLibraryCopy,
  formatExcelUploadDescription,
  formatFileLibraryCount,
  formatFileMetadata,
  formatPdfUploadDescription,
  getFileLibraryEmptyState,
} from '../src/features/file-library/domain-presentation.ts'

const excelFilePanelSource = readFileSync(
  new URL('../src/features/file-management/components/FileSourcePanel.vue', import.meta.url),
  'utf8',
)
const pdfFilePanelSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfManagementFilePane.vue',
    import.meta.url,
  ),
  'utf8',
)

test('uses parallel workspace and search copy for Excel and PDF files', () => {
  assert.equal(fileLibraryCopy.excel.workspaceTitle, 'Excel Files')
  assert.equal(fileLibraryCopy.pdf.workspaceTitle, 'PDF Files')
  assert.equal(fileLibraryCopy.excel.searchPlaceholder, 'Search Excel files...')
  assert.equal(fileLibraryCopy.pdf.searchPlaceholder, 'Search PDF files...')
})

test('formats domain-specific counts with correct singular and plural nouns', () => {
  assert.equal(formatFileLibraryCount('excel', 1), '1 workbook')
  assert.equal(formatFileLibraryCount('excel', 2), '2 workbooks')
  assert.equal(formatFileLibraryCount('pdf', 1), '1 source')
  assert.equal(formatFileLibraryCount('pdf', 2), '2 sources')
})

test('uses consistent empty-state structure while preserving domain meaning', () => {
  assert.deepEqual(getFileLibraryEmptyState('excel', false), {
    title: 'No Excel workbooks yet',
    detail: 'Upload an Excel workbook to create searchable sheets and rows.',
  })
  assert.deepEqual(getFileLibraryEmptyState('pdf', true), {
    title: 'No matching PDF sources',
    detail: 'Try another file name or clear the search.',
  })
})

test('formats upload descriptions from the same information template', () => {
  assert.equal(
    formatExcelUploadDescription(['.xls', '.xlsx'], '50MB'),
    'XLS, XLSX · Max 50MB each · Parsed into sheets and searchable rows.',
  )
  assert.equal(
    formatPdfUploadDescription('Compliance', '50 MB'),
    'PDF · Max 50 MB each · Uploaded to Compliance and indexed for cited answers.',
  )
})

test('joins file metadata with one shared separator and removes blank values', () => {
  assert.equal(
    formatFileMetadata(['PDF', '', 'Updated Aug 5', undefined, 'Ready']),
    'PDF · Updated Aug 5 · Ready',
  )
})

test('keeps both file panels wired to the centralized copy contract', () => {
  assert.ok(excelFilePanelSource.includes('fileLibraryCopy.excel'))
  assert.ok(pdfFilePanelSource.includes('fileLibraryCopy.pdf'))
  assert.equal(excelFilePanelSource.includes('Files Found'), false)
  assert.equal(pdfFilePanelSource.includes('Items Found'), false)
  assert.equal(pdfFilePanelSource.includes('Choose PDF files to upload'), false)
})
