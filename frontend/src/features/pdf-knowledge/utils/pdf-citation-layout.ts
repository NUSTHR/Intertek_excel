// Keep this boundary aligned with the PDF citation overlay media query.
export const PDF_CITATION_OVERLAY_MAX_WIDTH = 1180

export function shouldDefaultCollapsePdfCitations(viewportWidth: number): boolean {
  return viewportWidth <= PDF_CITATION_OVERLAY_MAX_WIDTH
}
