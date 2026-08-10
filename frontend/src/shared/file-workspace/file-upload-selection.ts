import type { FileUploadSelection } from '../../types/file-upload'

type FileWithRelativePath = File & { webkitRelativePath?: string }

export function toFileUploadSelection(
  file: File,
  relativePath?: string,
): FileUploadSelection {
  const browserRelativePath = (file as FileWithRelativePath).webkitRelativePath
  return {
    file,
    relativePath: normalizeUploadRelativePath(
      relativePath || browserRelativePath || file.name,
      file.name,
    ),
  }
}

export function normalizeUploadRelativePath(value: string, fallbackName: string): string {
  const normalizedParts = value
    .replace(/\\/g, '/')
    .split('/')
    .map((part) => part.trim())
    .filter((part) => part && part !== '.' && part !== '..' && !part.endsWith(':'))

  if (normalizedParts.length > 0) {
    return normalizedParts.join('/')
  }

  const fallback = fallbackName.trim().split(/[\\/]/).filter(Boolean).at(-1)
  return fallback || 'upload'
}
