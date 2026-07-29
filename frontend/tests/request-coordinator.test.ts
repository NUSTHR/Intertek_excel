import assert from 'node:assert/strict'
import test from 'node:test'

import { createRequestCoordinator } from '../src/app/composables/use-request-coordinator.ts'

test('starting a newer request aborts and invalidates the previous request', () => {
  const coordinator = createRequestCoordinator()
  const first = coordinator.begin()
  const second = coordinator.begin()

  assert.equal(first.signal.aborted, true)
  assert.equal(first.isCurrent(), false)
  assert.equal(second.signal.aborted, false)
  assert.equal(second.isCurrent(), true)
})

test('cancelling invalidates the active request immediately', () => {
  const coordinator = createRequestCoordinator()
  const request = coordinator.begin()

  coordinator.cancel()

  assert.equal(request.signal.aborted, true)
  assert.equal(request.isCurrent(), false)
})
