import type { LlmModelOptionsResponse, LlmPreference } from '../types/llm'
import { defaultRequestOptions } from './config'
import { requestJson } from './errors'

export async function getLlmModelOptions(): Promise<LlmModelOptionsResponse> {
  return requestJson<LlmModelOptionsResponse>(
    '/api/excel/llm/options',
    { method: 'GET' },
    defaultRequestOptions,
  )
}

export async function getLlmPreference(): Promise<LlmPreference> {
  return requestJson<LlmPreference>(
    '/api/excel/llm/preferences',
    { method: 'GET' },
    defaultRequestOptions,
  )
}

export async function saveLlmPreference(
  preference: Omit<LlmPreference, 'scope' | 'created_at' | 'updated_at'>,
): Promise<LlmPreference> {
  return requestJson<LlmPreference>(
    '/api/excel/llm/preferences',
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(preference),
    },
    defaultRequestOptions,
  )
}
