import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

const workspace = source('../src/app/ExcelWorkspaceApp.vue')
const baseActionMenu = source(
  '../src/shared/file-workspace/components/BaseActionMenu.vue',
)
const baseFileRow = source('../src/shared/file-workspace/components/BaseFileRow.vue')
const chatPanel = source('../src/components/ChatPanel.vue')
const chatDataSourceMenu = source(
  '../src/features/chat/components/ChatDataSourceMenu.vue',
)
const pdfDocumentInsight = source(
  '../src/features/pdf-knowledge/composables/use-pdf-document-insight.ts',
)
const pdfInsightPane = source(
  '../src/features/pdf-knowledge/components/PdfManagementInsightPane.vue',
)

test('action menus own their complete trigger and popover event boundary', () => {
  assert.ok(baseActionMenu.includes('ref="containerRef"'))
  assert.ok(baseActionMenu.includes('useOutsideClose'))
  assert.ok(baseActionMenu.includes('@click.stop="emit(\'toggle\')"'))
  assert.ok(baseFileRow.includes('<BaseActionMenu'))
  assert.ok(workspace.includes('<BaseActionMenu'))
})

test('the workspace root no longer races shared menus with a second document listener', () => {
  assert.equal(workspace.includes("document.addEventListener('pointerdown'"), false)
  assert.equal(workspace.includes('isActionMenuTarget'), false)
  assert.equal(workspace.includes('handleDocumentPointerDown'), false)
})

test('stopping a chat removes the optimistic turn before restoring its draft', () => {
  const stopStart = chatPanel.indexOf('async function stopCurrentAnswer')
  const stopEnd = chatPanel.indexOf('function removeHistoryEntry', stopStart)
  const stopSource = chatPanel.slice(stopStart, stopEnd)
  const removeIndex = stopSource.indexOf('removeHistoryEntry(pendingEntry)')
  const restoreIndex = stopSource.indexOf('question.value = restoredQuestion')
  assert.ok(removeIndex >= 0)
  assert.ok(restoreIndex > removeIndex)
  assert.ok(stopSource.includes("requestPhase.value = 'cancelling'"))
  assert.ok(stopSource.includes("requestPhase.value = 'idle'"))
})

test('latest chat turn exposes the established edit and regenerate actions', () => {
  assert.ok(chatPanel.includes('aria-label="Edit latest question"'))
  assert.ok(chatPanel.includes('@click="editLatestQuestion"'))
  assert.ok(chatPanel.includes('<span>Edit</span>'))
  assert.ok(chatPanel.includes('aria-label="Regenerate latest answer"'))
  assert.ok(chatPanel.includes('@click="regenerateLatestAnswer"'))
  assert.ok(chatPanel.includes('<span>Regenerate</span>'))
})

test('previous no-op controls now expose deterministic actions', () => {
  assert.ok(chatPanel.includes('<ChatDataSourceMenu'))
  assert.ok(chatDataSourceMenu.includes('@click="isOpen = !isOpen"'))
  assert.ok(chatDataSourceMenu.includes("emit('select', document)"))
  assert.ok(workspace.includes('aria-label="Search sheet data"'))
  assert.ok(workspace.includes('aria-label="Notifications" @click="showNotificationsNotice"'))
  assert.ok(workspace.includes("showChatSessionFeedback('info', message)"))
})

test('PDF summary state survives navigation without exposing task bookkeeping', () => {
  assert.ok(pdfDocumentInsight.includes('listPdfSummaryTasks'))
  assert.ok(pdfDocumentInsight.includes('restoreSummaryTasks'))
  assert.ok(pdfDocumentInsight.includes("summaryPhase.value = 'polling'"))
  assert.ok(pdfDocumentInsight.includes('summaryTargetFileIds'))
  assert.ok(pdfDocumentInsight.includes('shouldForceSummaryRegeneration'))
  assert.equal(pdfInsightPane.includes('summaryTaskResultLabel'), false)
  assert.equal(pdfInsightPane.includes('cancelSummaryTask'), false)
  assert.equal(pdfInsightPane.includes('retrySummaryTask'), false)
})
