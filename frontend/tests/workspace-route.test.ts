import assert from 'node:assert/strict'
import test from 'node:test'

import {
  activeViewFromHash,
  activeViewHash,
  canAccessWorkspaceDestination,
  defaultWorkspaceDestination,
  isCanonicalWorkspaceHash,
  isChatDestination,
  isFileDestination,
  isPdfDestination,
} from '../src/app/workspace-route.ts'

test('workspace hashes map to their supported views', () => {
  assert.equal(activeViewFromHash('#excel-chat'), 'excel-chat')
  assert.equal(activeViewFromHash('#pdf-chat'), 'pdf-chat')
  assert.equal(activeViewFromHash('#excel-files'), 'excel-files')
  assert.equal(activeViewFromHash('#pdf-files'), 'pdf-files')
  assert.equal(activeViewFromHash('#pdf-diagnostics'), 'pdf-diagnostics')
})

test('legacy hashes map to canonical destinations without changing business state', () => {
  assert.equal(activeViewFromHash('#chat'), 'excel-chat')
  assert.equal(activeViewFromHash('#files'), 'excel-files')
  assert.equal(activeViewFromHash('#pdf'), 'pdf-files')
  assert.equal(isCanonicalWorkspaceHash('#chat'), false)
  assert.equal(isCanonicalWorkspaceHash('#excel-chat'), true)
})

test('unknown and empty hashes safely fall back to Excel chat', () => {
  assert.equal(activeViewFromHash(''), 'excel-chat')
  assert.equal(activeViewFromHash('#unknown'), 'excel-chat')
})

test('workspace views serialize to canonical hashes', () => {
  assert.equal(activeViewHash('excel-chat'), '#excel-chat')
  assert.equal(activeViewHash('pdf-chat'), '#pdf-chat')
  assert.equal(activeViewHash('excel-files'), '#excel-files')
  assert.equal(activeViewHash('pdf-files'), '#pdf-files')
  assert.equal(activeViewHash('pdf-diagnostics'), '#pdf-diagnostics')
})

test('destination helpers preserve the global navigation and permission contract', () => {
  assert.equal(isChatDestination('excel-chat'), true)
  assert.equal(isChatDestination('pdf-chat'), true)
  assert.equal(isFileDestination('excel-files'), true)
  assert.equal(isFileDestination('pdf-files'), true)
  assert.equal(isPdfDestination('pdf-chat'), true)
  assert.equal(isPdfDestination('pdf-files'), true)
  assert.equal(isPdfDestination('excel-chat'), false)
  assert.equal(canAccessWorkspaceDestination('excel-chat', false), true)
  assert.equal(canAccessWorkspaceDestination('pdf-chat', false), true)
  assert.equal(canAccessWorkspaceDestination('excel-files', false), false)
  assert.equal(canAccessWorkspaceDestination('pdf-files', false), false)
  assert.equal(canAccessWorkspaceDestination('pdf-diagnostics', true), true)
  assert.equal(defaultWorkspaceDestination('excel-files'), 'excel-chat')
  assert.equal(defaultWorkspaceDestination('pdf-files'), 'pdf-chat')
})
