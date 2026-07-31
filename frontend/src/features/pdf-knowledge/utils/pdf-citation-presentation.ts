const PDF_PRIVATE_USE_BULLET = /\uF06E/g

export function optionalTrimmedText(
  value: string | null | undefined,
): string | undefined {
  const normalized = value?.trim()
  return normalized || undefined
}

export function normalizePdfDisplayText(value: string): string {
  return value.replace(PDF_PRIVATE_USE_BULLET, '•')
}

export function pdfCitationMatchLabel(
  pageLabel: string | null | undefined,
  chunkIndex: number,
): string {
  return optionalTrimmedText(pageLabel) ?? `Chunk ${chunkIndex + 1}`
}

export function pdfCitationLocationLabel(
  pageLabel: string | null | undefined,
  chunkIndex: number,
): string {
  const normalizedPageLabel = optionalTrimmedText(pageLabel)
  const chunkLabel = `Chunk ${chunkIndex + 1}`
  return normalizedPageLabel
    ? `${normalizedPageLabel} · ${chunkLabel}`
    : chunkLabel
}

export function pdfCitationCountLabel(count: number): string {
  return count === 1 ? 'Citation' : 'Citations'
}
