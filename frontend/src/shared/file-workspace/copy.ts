import type { FileDomain } from './file-card-contract'

const domainNouns: Record<FileDomain, { singular: string; plural: string }> = {
  excel: { singular: 'workbook', plural: 'workbooks' },
  pdf: { singular: 'PDF source', plural: 'PDF sources' },
}

export const fileWorkspaceCopy = {
  tabs: {
    summary: 'Summary',
    preview: 'Data Preview',
    schema: 'Schema',
  },
  modelConfiguration: 'Model Configuration',
  summaryTitle: 'AI Executive Summary',
  actions: {
    rename: 'Rename',
    delete: 'Delete',
    hide: 'Hide from members',
    show: 'Show to members',
    previous: 'Previous',
    next: 'Next',
  },
} as const

export function summaryEmptyCopy(
  domain: FileDomain,
  hasSelection = false,
): { title: string; detail: string } {
  const noun = domainNouns[domain].singular
  return {
    title: 'No summary generated',
    detail: hasSelection
      ? `Generate a summary for the selected ${noun} to view AI insights.`
      : `Select a ${noun} and generate a summary to view AI insights.`,
  }
}

export function loadingFilesCopy(domain: FileDomain): { title: string; detail: string } {
  return {
    title: `Loading ${domainNouns[domain].plural}`,
    detail: 'Refreshing the current file library.',
  }
}
