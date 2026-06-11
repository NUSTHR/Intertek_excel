import type { LlmModelOptionsResponse, LlmPreference } from '../types/llm'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''

export async function getLlmModelOptions(): Promise<LlmModelOptionsResponse> {
  const response = await fetch(`${apiBaseUrl}/api/excel/llm/options`, {
    method: 'GET',
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as LlmModelOptionsResponse
}

export async function getLlmPreference(): Promise<LlmPreference> {
  const response = await fetch(`${apiBaseUrl}/api/excel/llm/preferences`, {
    method: 'GET',
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as LlmPreference
}

export async function saveLlmPreference(
  preference: Omit<LlmPreference, 'scope' | 'created_at' | 'updated_at'>,
): Promise<LlmPreference> {
  const response = await fetch(`${apiBaseUrl}/api/excel/llm/preferences`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(preference),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as LlmPreference
}
