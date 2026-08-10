import assert from 'node:assert/strict'
import test from 'node:test'

import { matchesAccept, parseAccept } from '../src/shared/file-workspace/file-accept.ts'

test('parses extension clauses', () => {
  const result = parseAccept('.pdf,.xlsx')
  assert.deepEqual(result, [
    { kind: 'extension', value: '.pdf' },
    { kind: 'extension', value: '.xlsx' },
  ])
})

test('parses MIME clauses', () => {
  const result = parseAccept('application/pdf,text/csv')
  assert.deepEqual(result, [
    { kind: 'mime', value: 'application/pdf' },
    { kind: 'mime', value: 'text/csv' },
  ])
})

test('parses wildcard MIME clauses', () => {
  const result = parseAccept('image/*')
  assert.deepEqual(result, [{ kind: 'glob', subtype: 'image' }])
})

test('an empty accept matches any file', () => {
  assert.equal(parseAccept('').length, 0)
  const file = new File(['x'], 'a.pdf', { type: 'application/pdf' })
  assert.equal(matchesAccept(file, parseAccept('')), true)
})

test('matches by extension (case-insensitive)', () => {
  const file = new File(['x'], 'Manual.PDF', { type: '' })
  const clauses = parseAccept('.pdf')
  assert.equal(matchesAccept(file, clauses), true)
})

test('rejects files that do not match any clause', () => {
  const file = new File(['x'], 'manual.docx', { type: '' })
  const clauses = parseAccept('.pdf')
  assert.equal(matchesAccept(file, clauses), false)
})

test('matches by exact MIME type', () => {
  const file = new File(['x'], 'a.csv', { type: 'text/csv' })
  const clauses = parseAccept('text/csv')
  assert.equal(matchesAccept(file, clauses), true)
})

test('matches by wildcard subtype', () => {
  const file = new File(['x'], 'a.png', { type: 'image/png' })
  const clauses = parseAccept('image/*')
  assert.equal(matchesAccept(file, clauses), true)
})

test('rejects when the subtype does not match', () => {
  const file = new File(['x'], 'a.pdf', { type: 'application/pdf' })
  const clauses = parseAccept('image/*')
  assert.equal(matchesAccept(file, clauses), false)
})
