export type FileLibraryDomain = 'excel' | 'pdf'

export interface FileLibraryCopyTemplate {
  workspaceTitle: string
  searchLabel: string
  searchPlaceholder: string
  listTitle: string
  uploadTitle: string
  uploadPendingTitle: string
  emptyTitle: string
  emptyDetail: string
  searchEmptyTitle: string
  searchEmptyDetail: string
}

export interface FileLibraryEmptyStateCopy {
  title: string
  detail: string
}

export const fileLibraryCopy = {
  excel: {
    workspaceTitle: 'Excel Files',
    searchLabel: 'Search Excel files',
    searchPlaceholder: 'Search Excel files...',
    listTitle: 'Excel Files',
    uploadTitle: 'Upload Excel workbooks',
    uploadPendingTitle: 'Preparing Excel upload...',
    emptyTitle: 'No Excel workbooks yet',
    emptyDetail: 'Upload an Excel workbook to create searchable sheets and rows.',
    searchEmptyTitle: 'No matching Excel workbooks',
    searchEmptyDetail: 'Try another file name or clear the search.',
  },
  pdf: {
    workspaceTitle: 'PDF Files',
    searchLabel: 'Search PDF files',
    searchPlaceholder: 'Search PDF files...',
    listTitle: 'PDF Files',
    uploadTitle: 'Upload PDF documents',
    uploadPendingTitle: 'Preparing PDF uploads...',
    emptyTitle: 'No PDF sources yet',
    emptyDetail: 'Upload a PDF document to parse and index it for cited answers.',
    searchEmptyTitle: 'No matching PDF sources',
    searchEmptyDetail: 'Try another file name or clear the search.',
  },
} as const satisfies Record<FileLibraryDomain, FileLibraryCopyTemplate>

export const PDF_FILES_ROOT_LABEL = fileLibraryCopy.pdf.listTitle

export function formatFileLibraryCount(_domain: FileLibraryDomain, count: number): string {
  const normalizedCount = Math.max(0, count)
  const noun = normalizedCount === 1 ? 'workbook' : 'workbooks'
  return `${normalizedCount} ${noun}`
}

export function getFileLibraryEmptyState(
  domain: FileLibraryDomain,
  hasSearchQuery: boolean,
): FileLibraryEmptyStateCopy {
  const copy = fileLibraryCopy[domain]
  return hasSearchQuery
    ? { title: copy.searchEmptyTitle, detail: copy.searchEmptyDetail }
    : { title: copy.emptyTitle, detail: copy.emptyDetail }
}

export function formatExcelUploadDescription(
  allowedExtensions: string[],
  maxSize: string,
): string {
  const fileTypes = allowedExtensions
    .map((extension) => extension.trim().replace(/^\./, '').toUpperCase())
    .filter(Boolean)
    .join(', ')
  return `${fileTypes || 'Excel'} · Max ${maxSize} each · Parsed into sheets and searchable rows.`
}

export function formatPdfUploadDescription(scopeLabel: string, maxSize: string): string {
  const scope = scopeLabel.trim() || PDF_FILES_ROOT_LABEL
  return `PDF · Max ${maxSize} each · Uploaded to ${scope} and indexed for cited answers.`
}

export function formatFileMetadata(parts: Array<string | null | undefined>): string {
  return parts
    .map((part) => part?.trim() ?? '')
    .filter(Boolean)
    .join(' · ')
}
