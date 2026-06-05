import type {
  ActiveExcelFileResponse,
  DeleteExcelFileResponse,
  ExcelFile,
  ExcelFileVersion,
  ExcelSheet,
  ListExcelArtifactsResponse,
  ListExcelFilesResponse,
  ListExcelSheetsResponse,
  ListExcelVersionsResponse,
  RowLookupResponse,
  SheetRowsResponse,
  SheetPreviewResponse,
  UploadExcelResponse,
  WorkbookProfile,
} from '../types/excel-assets'

interface ErrorPayload {
  detail?: string
  requires_confirmation?: boolean
}

export class ExcelWorkspaceApiError extends Error {
  readonly statusCode: number | null
  readonly requiresConfirmation: boolean

  constructor(
    message: string,
    statusCode: number | null = null,
    requiresConfirmation = false,
  ) {
    super(message)
    this.name = 'ExcelWorkspaceApiError'
    this.statusCode = statusCode
    this.requiresConfirmation = requiresConfirmation
  }
}

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''
const requestTimeoutMs = Number(
  import.meta.env.VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS ?? 30000,
)

function createTimeoutSignal(): {
  signal: AbortSignal
  dispose: () => void
} {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs)
  return {
    signal: controller.signal,
    dispose: () => window.clearTimeout(timeoutId),
  }
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const timeout = createTimeoutSignal()
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      signal: timeout.signal,
    })
    if (!response.ok) {
      const payload = await parseErrorPayload(response)
      throw new ExcelWorkspaceApiError(
        payload.detail || `Request failed with status ${response.status}.`,
        response.status,
        payload.requires_confirmation === true,
      )
    }
    return (await response.json()) as T
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError) {
      throw error
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ExcelWorkspaceApiError('Request timed out.')
    }
    throw new ExcelWorkspaceApiError('Network error. Check whether the Excel backend is running.')
  } finally {
    timeout.dispose()
  }
}

async function parseErrorPayload(response: Response): Promise<ErrorPayload> {
  const text = await response.text()
  if (!text) {
    return {}
  }
  try {
    return JSON.parse(text) as ErrorPayload
  } catch {
    return { detail: text }
  }
}

export async function uploadExcelFile(
  file: File,
  replaceExisting: boolean,
): Promise<UploadExcelResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('replace_existing', String(replaceExisting))
  return requestJson<UploadExcelResponse>('/api/excel/files', {
    method: 'POST',
    body: formData,
  })
}

export async function listExcelFiles(): Promise<ExcelFile[]> {
  const response = await requestJson<ListExcelFilesResponse>('/api/excel/files', {
    method: 'GET',
  })
  return response.files
}

export async function deleteExcelFile(
  fileId: string,
  confirmDelete = false,
): Promise<DeleteExcelFileResponse> {
  const params = new URLSearchParams({
    confirm_delete: String(confirmDelete),
  })
  return requestJson<DeleteExcelFileResponse>(
    `/api/excel/files/${fileId}?${params.toString()}`,
    {
      method: 'DELETE',
    },
  )
}

export async function listExcelVersions(fileId: string): Promise<ExcelFileVersion[]> {
  const response = await requestJson<ListExcelVersionsResponse>(
    `/api/excel/files/${fileId}/versions`,
    {
      method: 'GET',
    },
  )
  return response.versions
}

export async function getActiveExcelFile(fileId: string): Promise<ActiveExcelFileResponse> {
  return requestJson<ActiveExcelFileResponse>(`/api/excel/files/${fileId}/active`, {
    method: 'GET',
  })
}

export async function listExcelSheets(versionId: string): Promise<ExcelSheet[]> {
  const response = await requestJson<ListExcelSheetsResponse>(
    `/api/excel/versions/${versionId}/sheets`,
    {
      method: 'GET',
    },
  )
  return response.sheets
}

export async function getExcelVersionProfile(versionId: string): Promise<WorkbookProfile> {
  return requestJson<WorkbookProfile>(`/api/excel/versions/${versionId}/profile`, {
    method: 'GET',
  })
}

export async function listExcelArtifacts(versionId: string): Promise<ListExcelArtifactsResponse> {
  return requestJson<ListExcelArtifactsResponse>(
    `/api/excel/versions/${versionId}/artifacts`,
    {
      method: 'GET',
    },
  )
}

export async function previewExcelSheet(
  sheetId: string,
  offset = 0,
  limit = 500,
): Promise<SheetPreviewResponse> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  })
  return requestJson<SheetPreviewResponse>(
    `/api/excel/sheets/${sheetId}/preview?${params.toString()}`,
    {
      method: 'GET',
    },
  )
}

export async function listExcelSheetRows(
  sheetId: string,
  offset = 0,
  limit = 500,
): Promise<SheetRowsResponse> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  })
  return requestJson<SheetRowsResponse>(
    `/api/excel/sheets/${sheetId}/rows?${params.toString()}`,
    {
      method: 'GET',
    },
  )
}

export async function lookupExcelRow(
  sheetId: string,
  rowId: string,
): Promise<RowLookupResponse> {
  return requestJson<RowLookupResponse>(
    `/api/excel/sheets/${sheetId}/rows/${encodeURIComponent(rowId)}`,
    {
      method: 'GET',
    },
  )
}
