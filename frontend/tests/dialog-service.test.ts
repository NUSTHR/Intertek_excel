import assert from 'node:assert/strict'
import test from 'node:test'
import { nextTick } from 'vue'

import {
  buildDeleteDialog,
  buildRenameDialog,
  buildUploadDialog,
  createDialogService,
} from '../src/shared/file-workspace/composables/use-dialog-service.ts'
import type { DialogTarget } from '../src/shared/file-workspace/dialog-contract.ts'

function excelTarget(): DialogTarget {
  return {
    domain: 'excel',
    id: 'xlsx-1',
    displayName: 'quarterly.xlsx',
    kindLabel: 'Excel Workbook',
  }
}

function pdfTarget(): DialogTarget {
  return {
    domain: 'pdf',
    id: 'pdf-1',
    displayName: 'manual.pdf',
    kindLabel: 'PDF Source',
  }
}

test('open() returns a promise that resolves with the user action', async () => {
  const service = createDialogService()
  const pending = service.open(buildRenameDialog(excelTarget(), 'new-name'))
  await nextTick()
  assert.equal(service.current.value?.kind, 'rename')

  service.submitRename('new-name')
  const result = await pending
  assert.deepEqual(result, { kind: 'rename', action: 'submit', draft: 'new-name' })
  assert.equal(service.current.value, null)
})

test('consecutive open() calls do not leak draft from a previous rename', async () => {
  const service = createDialogService()
  const first = service.open(buildRenameDialog(excelTarget(), 'a'))
  service.close()
  const firstResult = await first
  assert.deepEqual(firstResult, { kind: 'rename', action: 'cancel' })

  const second = service.open(buildRenameDialog(pdfTarget(), 'b'))
  assert.equal(service.current.value?.kind, 'rename')
  if (service.current.value?.kind === 'rename') {
    assert.equal(service.current.value.draft, 'b')
    assert.equal(service.current.value.target.domain, 'pdf')
  }
  service.close()
  await second
})

test('submitRename() rejects empty drafts and surfaces an error message', async () => {
  const service = createDialogService()
  const pending = service.open(buildRenameDialog(excelTarget(), 'ok'))
  // The user clears the field, which updates the draft via the input
  // binding. The submit call then validates the trimmed value.
  service.setRenameDraft('   ')
  service.submitRename('   ')
  await nextTick()
  assert.equal(service.current.value?.kind, 'rename')
  if (service.current.value?.kind === 'rename') {
    assert.equal(service.current.value.errorMessage, 'Name cannot be empty.')
    assert.equal(service.current.value.draft, '   ')
  }
  service.close()
  await pending
})

test('setError() does not change the dialog kind', async () => {
  const service = createDialogService()
  const pending = service.open(buildDeleteDialog(pdfTarget()))
  service.setError('Cannot delete right now.')
  await nextTick()
  assert.equal(service.current.value?.kind, 'delete')
  if (service.current.value?.kind === 'delete') {
    assert.equal(service.current.value.errorMessage, 'Cannot delete right now.')
  }
  service.close()
  await pending
})

test('confirmDelete() resolves with confirm and clears the queue', async () => {
  const service = createDialogService()
  const pending = service.open(buildDeleteDialog(excelTarget()))
  service.confirmDelete()
  const result = await pending
  assert.deepEqual(result, { kind: 'delete', action: 'confirm' })
  assert.equal(service.current.value, null)
})

test('confirmUpload() resolves with confirm and clears the queue', async () => {
  const service = createDialogService()
  const pending = service.open(
    buildUploadDialog(
      { domain: 'excel', file: { name: 'a.xlsx', sizeBytes: 1234 }, kind: 'new' },
    ),
  )
  service.confirmUpload()
  const result = await pending
  assert.deepEqual(result, { kind: 'upload', action: 'confirm' })
})

test('close() while a dialog is open resolves the pending promise as cancel', async () => {
  const service = createDialogService()
  const pending = service.open(buildRenameDialog(excelTarget(), 'x'))
  service.close()
  const result = await pending
  assert.deepEqual(result, { kind: 'rename', action: 'cancel' })
})

test('opening a new dialog while one is in flight resolves the previous as cancel', async () => {
  const service = createDialogService()
  const first = service.open(buildDeleteDialog(excelTarget()))
  const second = service.open(buildRenameDialog(pdfTarget(), 'second'))
  const firstResult = await first
  assert.deepEqual(firstResult, { kind: 'delete', action: 'cancel' })
  assert.equal(service.current.value?.kind, 'rename')
  service.close()
  await second
})
