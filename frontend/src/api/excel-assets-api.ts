import type {
  ActiveExcelFileResponse,
  CreateUploadTaskResponse,
  DeleteExcelFileResponse,
  ExcelFile,
  ExcelFileVersion,
  ExcelSheet,
  ListExcelArtifactsResponse,
  ListExcelFilesResponse,
  ListExcelSheetsResponse,
  ListExcelVersionsResponse,
  RowLookupResponse,
  SheetPreviewResponse,
  SheetSearchResponse,
  SheetRowsResponse,
  UploadExcelResponse,
  UploadTaskResponse,
  WorkbookProfile,
  WorkbookSearchResponse,
} from '../types/excel-assets'
import { defaultRequestOptions } from './config'
import { requestJson, type RequestOptions } from './errors'

export { ExcelWorkspaceApiError } from './errors'

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
    defaultRequestOptions,
  )
}

export async function createUploadTask(
  file: File,
  replaceExisting: boolean,
): Promise<CreateUploadTaskResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('replace_existing', String(replaceExisting))
  return requestJson<CreateUploadTaskResponse>(
    '/api/excel/files/upload-tasks',
    {
      method: 'POST',
      body: formData,
    },
    defaultRequestOptions,
  )
}

export async function getUploadTask(taskId: string): Promise<UploadTaskResponse> {
  return requestJson<UploadTaskResponse>(
    `/api/excel/files/upload-tasks/${encodeURIComponent(taskId)}`,
    { method: 'GET' },
    defaultRequestOptions,
  )
}

export async function listExcelFiles(): Promise<ExcelFile[]> {
  const response = await requestJson<ListExcelFilesResponse>(
    '/api/excel/files',
    { method: 'GET' },
    defaultRequestOptions,
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
    defaultRequestOptions,
  )
}

export async function setExcelFileVisibility(
  fileId: string,
  visibleToMembers: boolean,
): Promise<ExcelFile> {
  return requestJson<ExcelFile>(
    `/api/excel/files/${fileId}/visibility`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ visible_to_members: visibleToMembers }),
    },
    defaultRequestOptions,
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
    defaultRequestOptions,
  )
}

export async function listExcelVersions(fileId: string): Promise<ExcelFileVersion[]> {
  const response = await requestJson<ListExcelVersionsResponse>(
    `/api/excel/files/${fileId}/versions`,
    {
      method: 'GET',
    },
    defaultRequestOptions,
  )
  return response.versions
}

export async function getActiveExcelFile(fileId: string): Promise<ActiveExcelFileResponse> {
  return requestJson<ActiveExcelFileResponse>(
    `/api/excel/files/${fileId}/active`,
    { method: 'GET' },
    defaultRequestOptions,
  )
}

export async function listExcelSheets(versionId: string): Promise<ExcelSheet[]> {
  const response = await requestJson<ListExcelSheetsResponse>(
    `/api/excel/versions/${versionId}/sheets`,
    {
      method: 'GET',
    },
    defaultRequestOptions,
  )
  return response.sheets
}

export async function getExcelVersionProfile(versionId: string): Promise<WorkbookProfile> {
  return requestJson<WorkbookProfile>(
    `/api/excel/versions/${versionId}/profile`,
    { method: 'GET' },
    defaultRequestOptions,
  )
}

export async function listExcelArtifacts(versionId: string): Promise<ListExcelArtifactsResponse> {
  return requestJson<ListExcelArtifactsResponse>(
    `/api/excel/versions/${versionId}/artifacts`,
    {
      method: 'GET',
    },
    defaultRequestOptions,
  )
}

export async function previewExcelSheet(
  sheetId: string,
  offset = 0,
  limit = 500,
  options: RequestOptions = {},
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
    { ...defaultRequestOptions, ...options },
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
    defaultRequestOptions,
  )
}

export async function searchExcelSheetRows(
  sheetId: string,
  query: string,
  limit = 50,
  options: RequestOptions = {},
): Promise<SheetSearchResponse> {
  const params = new URLSearchParams({
    query,
    limit: String(limit),
  })
  return requestJson<SheetSearchResponse>(
    `/api/excel/sheets/${sheetId}/search?${params.toString()}`,
    {
      method: 'GET',
    },
    { ...defaultRequestOptions, ...options },
  )
}

export async function searchExcelVersionRows(
  versionId: string,
  query: string,
  limit = 50,
  options: RequestOptions = {},
): Promise<WorkbookSearchResponse> {
  const params = new URLSearchParams({
    query,
    limit: String(limit),
  })
  return requestJson<WorkbookSearchResponse>(
    `/api/excel/versions/${versionId}/search?${params.toString()}`,
    {
      method: 'GET',
    },
    { ...defaultRequestOptions, ...options },
  )
}

export async function lookupExcelRow(
  sheetId: string,
  rowId: string,
  options: RequestOptions = {},
): Promise<RowLookupResponse> {
  return requestJson<RowLookupResponse>(
    `/api/excel/sheets/${sheetId}/rows/${encodeURIComponent(rowId)}`,
    { method: 'GET' },
    { ...defaultRequestOptions, ...options },
  )
}
