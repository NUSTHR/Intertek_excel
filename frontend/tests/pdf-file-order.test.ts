import assert from 'node:assert/strict'
import test from 'node:test'

import { sortPdfFilesByNewest } from '../src/features/pdf-knowledge/utils/pdf-file-order.ts'
import type { PdfManagedFile } from '../src/features/pdf-knowledge/types.ts'

function pdfFile(
  id: string,
  createdAt: string,
  updatedAt = createdAt,
): PdfManagedFile {
  return {
    id,
    name: `${id}.pdf`,
    kind: 'pdf',
    createdAt,
    updatedAt,
    sizeLabel: '',
    modifiedLabel: '',
    status: 'ready',
    visibleToMembers: true,
  }
}

test('places newly created PDF files first regardless of processing status or name', () => {
  const newest = { ...pdfFile('z-new', '2026-07-29T10:00:00Z'), status: 'ready' as const }
  const oldest = { ...pdfFile('a-old', '2026-07-28T10:00:00Z'), status: 'uploading' as const }

  assert.deepEqual(
    sortPdfFilesByNewest([oldest, newest]).map((file) => file.id),
    ['z-new', 'a-old'],
  )
})

test('uses update time and id as deterministic ties without mutating source order', () => {
  const source = [
    pdfFile('b', '2026-07-29T10:00:00Z', '2026-07-29T11:00:00Z'),
    pdfFile('a', '2026-07-29T10:00:00Z', '2026-07-29T11:00:00Z'),
    pdfFile('c', '2026-07-29T10:00:00Z', '2026-07-29T12:00:00Z'),
  ]

  assert.deepEqual(
    sortPdfFilesByNewest(source).map((file) => file.id),
    ['c', 'a', 'b'],
  )
  assert.deepEqual(source.map((file) => file.id), ['b', 'a', 'c'])
})
