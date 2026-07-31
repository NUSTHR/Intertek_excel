import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PDF_CITATION_OVERLAY_MAX_WIDTH,
  shouldDefaultCollapsePdfCitations,
} from '../src/features/pdf-knowledge/utils/pdf-citation-layout.ts'

test('collapses citations whenever the responsive layout renders them as an overlay', () => {
  assert.equal(PDF_CITATION_OVERLAY_MAX_WIDTH, 1180)
  assert.equal(shouldDefaultCollapsePdfCitations(1180), true)
  assert.equal(shouldDefaultCollapsePdfCitations(952), true)
  assert.equal(shouldDefaultCollapsePdfCitations(861), true)
})

test('keeps citations expanded when the desktop grid has a dedicated citation column', () => {
  assert.equal(shouldDefaultCollapsePdfCitations(1181), false)
  assert.equal(shouldDefaultCollapsePdfCitations(1440), false)
})
