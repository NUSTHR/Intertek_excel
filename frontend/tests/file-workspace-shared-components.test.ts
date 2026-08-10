import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { summaryEmptyCopy } from '../src/shared/file-workspace/copy.ts'
import { FILE_WORKSPACE_PAGE_SIZE } from '../src/shared/file-workspace/file-pagination-contract.ts'

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const excelFiles = source('../src/features/file-management/components/FileSourcePanel.vue')
const pdfFiles = source('../src/features/pdf-knowledge/components/PdfManagementFilePane.vue')
const excelInsight = source('../src/features/file-management/components/FileInsightPane.vue')
const pdfInsight = source('../src/features/pdf-knowledge/components/PdfManagementInsightPane.vue')
const excelSummary = source('../src/features/file-management/components/FileSummaryPanel.vue')
const excelSummaryCard = source('../src/components/DocumentSummaryCard.vue')
const sharedSummaryCard = source(
  '../src/shared/file-workspace/components/BaseDocumentSummaryCard.vue',
)
const sharedPagination = source(
  '../src/shared/file-workspace/components/BaseFilePagination.vue',
)
const pdfManagement = source('../src/features/pdf-knowledge/components/PdfKnowledgeManagementWorkspace.vue')
const excelDialogs = source('../src/components/WorkspaceDialogs.vue')
const pdfLibrary = source('../src/features/pdf-knowledge/composables/use-pdf-knowledge-library.ts')
const dialogContract = source('../src/shared/file-workspace/dialog-contract.ts')
const mainSource = source('../src/main.ts')

test('Excel and PDF file lists render the same shared primitives', () => {
  for (const component of [
    'BaseFileLibraryHeading',
    'BaseFileDropzone',
    'BaseFileRow',
    'BaseFileState',
    'BaseFilePagination',
  ]) {
    assert.ok(excelFiles.includes(component), `Excel is missing ${component}`)
    assert.ok(pdfFiles.includes(component), `PDF is missing ${component}`)
  }
})

test('Excel and PDF insight navigation uses the same tabs and toolbar', () => {
  for (const component of ['BaseFileInsightTabs', 'BaseFileInsightToolbar']) {
    assert.ok(excelInsight.includes(component), `Excel is missing ${component}`)
    assert.ok(pdfInsight.includes(component), `PDF is missing ${component}`)
  }
  assert.ok(excelSummary.includes('BaseModelConfiguration'))
  assert.ok(pdfInsight.includes('BaseModelConfiguration'))
  assert.ok(excelSummary.includes('DocumentSummaryCard'))
  assert.ok(excelSummaryCard.includes('BaseDocumentSummaryCard'))
  assert.ok(pdfInsight.includes('BaseDocumentSummaryCard'))
  assert.ok(sharedSummaryCard.includes('document-summary-card'))
  assert.equal(pdfInsight.includes('unavailable'), false)
})

test('PDF management uses the PDF Files root label and the shared count contract', () => {
  assert.equal(pdfFiles.includes('Knowledge Base'), false)
  assert.ok(pdfFiles.includes('copy.listTitle'))
  assert.ok(pdfLibrary.includes('PDF_FILES_ROOT_LABEL'))
})

test('file dialogs share one renderer and PDF never uses a native prompt', () => {
  assert.ok(excelDialogs.includes('BaseWorkspaceDialog'))
  assert.ok(pdfManagement.includes('BaseWorkspaceDialog'))
  assert.equal(pdfManagement.includes('window.prompt'), false)
})

test('shared contracts stay independent from feature records', () => {
  assert.equal(dialogContract.includes('features/'), false)
  assert.equal(dialogContract.includes('ExcelFile'), false)
  assert.equal(dialogContract.includes('PdfManagedFile'), false)
})

test('both domains use the canonical page size and copy template', () => {
  assert.equal(FILE_WORKSPACE_PAGE_SIZE, 6)
  assert.ok(pdfLibrary.includes('FILE_WORKSPACE_PAGE_SIZE'))
  assert.equal(pdfLibrary.includes('pdfFilePageSize = 4'), false)
  assert.deepEqual(summaryEmptyCopy('excel'), {
    title: 'No summary generated',
    detail: 'Select a workbook and generate a summary to view AI insights.',
  })
  assert.deepEqual(summaryEmptyCopy('pdf'), {
    title: 'No summary generated',
    detail: 'Select a PDF source and generate a summary to view AI insights.',
  })
})

test('empty file libraries do not invent a page-one control', () => {
  assert.equal(excelFiles.includes('props.visiblePages : [1]'), false)
  assert.equal(pdfFiles.includes('props.visiblePages : [1]'), false)
  assert.ok(sharedPagination.includes('model.showNavigation'))
})

test('shared design tokens and component styles are part of the application bundle', () => {
  assert.ok(mainSource.includes("'./styles/file-workspace-domain.css'"))
  assert.ok(mainSource.includes("'./styles/file-workspace-base.css'"))
})
