import type { DocumentSummary, DocumentSummaryUpdate } from '../types/document-summary'
import { requestJson } from './errors'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''

async function requestSummary(path: string, init: RequestInit): Promise<DocumentSummary> {
  return requestJson<DocumentSummary>(path, init, { apiBaseUrl })
}

export async function generateDocumentSummary(
  versionId: string,
  model: string | null = null,
  provider: string | null = null,
): Promise<DocumentSummary> {
  return requestSummary(`/api/excel/versions/${versionId}/summary/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ model, provider }),
  })
}

export async function getDocumentSummary(versionId: string): Promise<DocumentSummary> {
  return requestSummary(`/api/excel/versions/${versionId}/summary`, {
    method: 'GET',
  })
}

export async function updateDocumentSummary(
  versionId: string,
  summary: DocumentSummaryUpdate,
): Promise<DocumentSummary> {
  return requestSummary(`/api/excel/versions/${versionId}/summary`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(summary),
  })
}
