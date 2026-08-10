import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPdfUploadFormData } from '../src/api/pdf-upload-form-data.ts'

test('places the selected folder path in the multipart filename', () => {
  const file = new File(['pdf'], 'manual.pdf', { type: 'application/pdf' })
  const body = buildPdfUploadFormData([
    { file, relativePath: 'Research/Guides/manual.pdf' },
  ])

  const uploaded = body.getAll('files')
  assert.equal(uploaded.length, 1)
  assert.ok(uploaded[0] instanceof File)
  assert.equal(uploaded[0].name, 'Research/Guides/manual.pdf')
})

test('trims the selected PDF parent folder id', () => {
  const body = buildPdfUploadFormData([], '  pdf-folder-1  ')
  assert.equal(body.get('parent_id'), 'pdf-folder-1')
})
