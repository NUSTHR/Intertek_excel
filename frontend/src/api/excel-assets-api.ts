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
export { ExcelWorkspaceApiError } from './errors'
import { requestJson } from './errors'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''
const requestTimeoutMs = Number(
  import.meta.env.VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS ?? 30000,
)

const requestOptions = {
  apiBaseUrl,
  timeoutMs: requestTimeoutMs,
}

export async function uploadExcelFile(
  file: File,
  replaceExisting: boolean,
): Promise<UploadExcelResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('replace_existing', String(replaceExisting))
  return requestJson<UploadExcelResponse>(
    '/api/excel/files',
    {
      method: 'POST',
      body: formData,
    },
    requestOptions,
  )
}

export async function listExcelFiles(): Promise<ExcelFile[]> {
  const response = await requestJson<ListExcelFilesResponse>(
    '/api/excel/files',
    { method: 'GET' },
    requestOptions,
  )
  return response.files
}

export async function renameExcelFile(
  fileId: string,
  displayName: string,
): Promise<ExcelFile> {
  return requestJson<ExcelFile>(
    `/api/excel/files/${fileId}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ display_name: displayName }),
    },
    requestOptions,
  )
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
    requestOptions,
  )
}

export async function listExcelVersions(fileId: string): Promise<ExcelFileVersion[]> {
  const response = await requestJson<ListExcelVersionsResponse>(
    `/api/excel/files/${fileId}/versions`,
    {
      method: 'GET',
    },
    requestOptions,
  )
  return response.versions
}

export async function getActiveExcelFile(fileId: string): Promise<ActiveExcelFileResponse> {
  return requestJson<ActiveExcelFileResponse>(
    `/api/excel/files/${fileId}/active`,
    { method: 'GET' },
    requestOptions,
  )
}

export async function listExcelSheets(versionId: string): Promise<ExcelSheet[]> {
  const response = await requestJson<ListExcelSheetsResponse>(
    `/api/excel/versions/${versionId}/sheets`,
    {
      method: 'GET',
    },
    requestOptions,
  )
  return response.sheets
}

export async function getExcelVersionProfile(versionId: string): Promise<WorkbookProfile> {
  return requestJson<WorkbookProfile>(
    `/api/excel/versions/${versionId}/profile`,
    { method: 'GET' },
    requestOptions,
  )
}

export async function listExcelArtifacts(versionId: string): Promise<ListExcelArtifactsResponse> {
  return requestJson<ListExcelArtifactsResponse>(
    `/api/excel/versions/${versionId}/artifacts`,
    {
      method: 'GET',
    },
    requestOptions,
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
    requestOptions,
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
    requestOptions,
  )
}

export async function lookupExcelRow(
  sheetId: string,
  rowId: string,
): Promise<RowLookupResponse> {
  return requestJson<RowLookupResponse>(
    `/api/excel/sheets/${sheetId}/rows/${encodeURIComponent(rowId)}`,
    { method: 'GET' },
    requestOptions,
  )
}
