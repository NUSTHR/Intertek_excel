import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPdfKnowledgeTree } from '../src/features/pdf-knowledge/utils/pdf-tree.ts'
import type { PdfManagedFile } from '../src/features/pdf-knowledge/types.ts'

function pdfFile(
  id: string,
  name: string,
  kind: PdfManagedFile['kind'],
  parentId?: string,
): PdfManagedFile {
  return {
    id,
    name,
    kind,
    parentId,
    createdAt: '',
    updatedAt: '',
    sizeLabel: '',
    modifiedLabel: '',
    status: 'ready',
    visibleToMembers: true,
  }
}

test('builds nested PDF nodes from one adjacency pass', () => {
  const tree = buildPdfKnowledgeTree([
    pdfFile('root', 'Root', 'folder'),
    pdfFile('nested', 'Nested', 'folder', 'root'),
    pdfFile('pdf', 'standard.pdf', 'pdf', 'nested'),
  ])

  assert.equal(tree.length, 1)
  assert.equal(tree[0]?.children?.[0]?.children?.[0]?.name, 'standard.pdf')
})

test('keeps orphaned and cyclic records visible without recursing forever', () => {
  const tree = buildPdfKnowledgeTree([
    pdfFile('orphan', 'Orphan.pdf', 'pdf', 'missing'),
    pdfFile('cycle-a', 'Cycle A', 'folder', 'cycle-b'),
    pdfFile('cycle-b', 'Cycle B', 'folder', 'cycle-a'),
  ])

  const rootNames = tree.map((node) => node.name)
  assert.ok(rootNames.includes('Orphan.pdf'))
  assert.ok(rootNames.includes('Cycle A') || rootNames.includes('Cycle B'))
})
