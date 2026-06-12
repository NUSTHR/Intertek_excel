import type { DocumentSummary, DocumentSummaryUpdate } from '../types/document-summary'
import { defaultRequestOptions } from './config'
import { requestJson } from './errors'

async function requestSummary(path: string, init: RequestInit): Promise<DocumentSummary> {
  return requestJson<DocumentSummary>(path, init, defaultRequestOptions)
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
