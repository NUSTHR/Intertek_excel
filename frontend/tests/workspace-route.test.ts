import assert from 'node:assert/strict'
import test from 'node:test'

import { activeViewFromHash, activeViewHash } from '../src/app/workspace-route.ts'

test('workspace hashes map to their supported views', () => {
  assert.equal(activeViewFromHash('#files'), 'files')
  assert.equal(activeViewFromHash('#pdf'), 'pdf')
  assert.equal(activeViewFromHash('#pdf-diagnostics'), 'pdf-diagnostics')
  assert.equal(activeViewFromHash('#chat'), 'chat')
})

test('unknown and empty hashes safely fall back to chat', () => {
  assert.equal(activeViewFromHash(''), 'chat')
  assert.equal(activeViewFromHash('#unknown'), 'chat')
})

test('workspace views serialize to canonical hashes', () => {
  assert.equal(activeViewHash('chat'), '#chat')
  assert.equal(activeViewHash('files'), '#files')
  assert.equal(activeViewHash('pdf'), '#pdf')
  assert.equal(activeViewHash('pdf-diagnostics'), '#pdf-diagnostics')
})
