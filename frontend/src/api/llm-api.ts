import type { LlmModelOptionsResponse } from '../types/llm'

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
