import assert from 'node:assert/strict'
import test from 'node:test'

import {
  hasPdfModelSettingErrors,
  validatePdfModelSetting,
} from '../src/features/pdf-knowledge/utils/pdf-model-setting.ts'
import type { PdfModelSetting } from '../src/features/pdf-knowledge/types.ts'

const baseSetting: PdfModelSetting = {
  id: 'summary',
  label: 'Summary Engine',
  providers: ['provider-a', 'provider-b'],
  models: ['model-a', 'model-b'],
  providerModels: {
    'provider-a': ['model-a'],
    'provider-b': ['model-b'],
  },
  selectedProvider: 'provider-a',
  selectedModel: 'model-a',
}

test('accepts a supported provider and model pair', () => {
  const errors = validatePdfModelSetting(baseSetting)

  assert.deepEqual(errors, {})
  assert.equal(hasPdfModelSettingErrors(errors), false)
})

test('marks only the model field when a provider change creates a temporary mismatch', () => {
  const errors = validatePdfModelSetting({
    ...baseSetting,
    selectedProvider: 'provider-b',
  })

  assert.equal(errors.selectedProvider, undefined)
  assert.equal(errors.selectedModel, 'Select a model supported by this provider.')
  assert.equal(hasPdfModelSettingErrors(errors), true)
})

test('marks an unknown provider without treating the draft as a valid pair', () => {
  const errors = validatePdfModelSetting({
    ...baseSetting,
    selectedProvider: 'unknown',
  })

  assert.equal(errors.selectedProvider, 'Select a supported provider.')
  assert.equal(errors.selectedModel, undefined)
})
