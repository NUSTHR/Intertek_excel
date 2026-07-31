import { ExcelWorkspaceApiError } from '../../../api/errors'

export function newRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `pdfreq_${crypto.randomUUID()}`
  }
  return `pdfreq_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
}

export function dedupeFileIds(fileIds: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const fileId of fileIds) {
    const normalized = fileId.trim()
    if (!normalized || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    result.push(normalized)
  }
  return result
}

export function sameFileIds(left: string[], right: string[]): boolean {
  return left.length === right.length
    && left.every((fileId, index) => fileId === right[index])
}

export function toErrorMessage(error: unknown, question = ''): string {
  const message = error instanceof Error ? error.message : 'PDF chat request failed.'
  if (
    error instanceof ExcelWorkspaceApiError
    && ['PDF_ROUTER_INVALID_RESPONSE', 'LLM_RESPONSE_INVALID'].includes(error.code)
  ) {
    return /[\u3400-\u9fff]/.test(question)
      ? 'PDF 文档路由暂时失败，请重试当前问题。'
      : 'PDF document routing temporarily failed. Please retry the question.'
  }
  return message
}
