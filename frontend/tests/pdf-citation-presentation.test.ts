import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizePdfDisplayText,
  optionalTrimmedText,
  pdfCitationCountLabel,
  pdfCitationLocationLabel,
  pdfCitationMatchLabel,
} from '../src/features/pdf-knowledge/utils/pdf-citation-presentation.ts'

test('treats blank optional labels as absent', () => {
  assert.equal(optionalTrimmedText('   '), undefined)
  assert.equal(optionalTrimmedText(null), undefined)
  assert.equal(optionalTrimmedText(' Page 4 '), 'Page 4')
})

test('falls back to the chunk label when the page label is blank', () => {
  assert.equal(pdfCitationMatchLabel('', 2), 'Chunk 3')
  assert.equal(pdfCitationMatchLabel('  ', 2), 'Chunk 3')
  assert.equal(pdfCitationMatchLabel('Page 7', 2), 'Page 7')
})

test('builds a compact location from page and chunk identifiers', () => {
  assert.equal(pdfCitationLocationLabel('Page 7', 2), 'Page 7 · Chunk 3')
  assert.equal(pdfCitationLocationLabel('', 2), 'Chunk 3')
})

test('normalizes the known MinerU private-use bullet for presentation', () => {
  assert.equal(
    normalizePdfDisplayText('\uF06E First item\nNormal text'),
    '• First item\nNormal text',
  )
  assert.equal(normalizePdfDisplayText('Normal text'), 'Normal text')
})

test('uses the correct citation count noun', () => {
  assert.equal(pdfCitationCountLabel(0), 'Citations')
  assert.equal(pdfCitationCountLabel(1), 'Citation')
  assert.equal(pdfCitationCountLabel(2), 'Citations')
})
