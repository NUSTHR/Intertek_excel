import type { FileUploadSelection } from '../types/file-upload'
import { normalizeUploadRelativePath } from '../shared/file-workspace/file-upload-selection.ts'

export function buildPdfUploadFormData(
  selections: FileUploadSelection[],
  parentId?: string,
): FormData {
  const body = new FormData()
  const normalizedParentId = parentId?.trim()
  if (normalizedParentId) {
    body.append('parent_id', normalizedParentId)
  }
  selections.forEach((selection) => {
    body.append(
      'files',
      selection.file,
      normalizeUploadRelativePath(selection.relativePath, selection.file.name),
    )
  })
  return body
}
