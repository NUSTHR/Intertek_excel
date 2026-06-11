import type { LlmModelOptionsResponse, LlmPreference } from '../types/llm'
import { requestJson } from './errors'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''

export async function getLlmModelOptions(): Promise<LlmModelOptionsResponse> {
  return requestJson<LlmModelOptionsResponse>(
    '/api/excel/llm/options',
    { method: 'GET' },
    { apiBaseUrl },
  )
}

export async function getLlmPreference(): Promise<LlmPreference> {
  return requestJson<LlmPreference>(
    '/api/excel/llm/preferences',
    { method: 'GET' },
    { apiBaseUrl },
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
    { apiBaseUrl },
  )
}
