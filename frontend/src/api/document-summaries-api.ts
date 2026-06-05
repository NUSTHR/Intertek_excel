import type { DocumentSummary } from '../types/document-summary'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''

async function requestSummary(path: string, init: RequestInit): Promise<DocumentSummary> {
  const response = await fetch(`${apiBaseUrl}${path}`, init)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as DocumentSummary
}

export async function generateDocumentSummary(versionId: string): Promise<DocumentSummary> {
  return requestSummary(`/api/excel/versions/${versionId}/summary/generate`, {
    method: 'POST',
  })
}

export async function getDocumentSummary(versionId: string): Promise<DocumentSummary> {
  return requestSummary(`/api/excel/versions/${versionId}/summary`, {
    method: 'GET',
  })
}
