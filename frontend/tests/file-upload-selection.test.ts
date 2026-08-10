import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeUploadRelativePath,
  toFileUploadSelection,
} from '../src/shared/file-workspace/file-upload-selection.ts'

test('normalizes folder paths without flattening their hierarchy', () => {
  assert.equal(
    normalizeUploadRelativePath('Research\\2026\\manual.pdf', 'manual.pdf'),
    'Research/2026/manual.pdf',
  )
})

test('removes traversal segments from upload paths', () => {
  assert.equal(
    normalizeUploadRelativePath('../Research/./manual.pdf', 'manual.pdf'),
    'Research/manual.pdf',
  )
})

test('uses the browser directory-relative path when available', () => {
  const file = new File(['pdf'], 'manual.pdf', { type: 'application/pdf' })
  Object.defineProperty(file, 'webkitRelativePath', {
    configurable: true,
    value: 'Knowledge/Nested/manual.pdf',
  })

  assert.deepEqual(toFileUploadSelection(file), {
    file,
    relativePath: 'Knowledge/Nested/manual.pdf',
  })
})

test('an explicit drag path takes precedence over browser metadata', () => {
  const file = new File(['pdf'], 'manual.pdf', { type: 'application/pdf' })
  Object.defineProperty(file, 'webkitRelativePath', {
    configurable: true,
    value: 'Picker/manual.pdf',
  })

  assert.equal(
    toFileUploadSelection(file, 'Dropped/Subfolder/manual.pdf').relativePath,
    'Dropped/Subfolder/manual.pdf',
  )
})
