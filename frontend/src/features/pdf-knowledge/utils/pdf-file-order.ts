import type { PdfManagedFile } from '../types'

export function sortPdfFilesByNewest(files: PdfManagedFile[]): PdfManagedFile[] {
  return [...files].sort((left, right) => {
    const createdAtDelta = right.createdAt.localeCompare(left.createdAt)
    if (createdAtDelta !== 0) {
      return createdAtDelta
    }
    const updatedAtDelta = right.updatedAt.localeCompare(left.updatedAt)
    if (updatedAtDelta !== 0) {
      return updatedAtDelta
    }
    return left.id.localeCompare(right.id)
  })
}
