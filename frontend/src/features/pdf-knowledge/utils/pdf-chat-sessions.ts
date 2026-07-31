import type { PdfChatSession, PdfRecentChat } from '../types.ts'

export function sortPdfChatSessions(
  sessions: readonly PdfChatSession[],
): PdfChatSession[] {
  return [...sessions].sort((left, right) => {
    if (left.pinnedAt && !right.pinnedAt) {
      return -1
    }
    if (!left.pinnedAt && right.pinnedAt) {
      return 1
    }
    const leftDate = left.pinnedAt || left.updatedAt
    const rightDate = right.pinnedAt || right.updatedAt
    const dateOrder = rightDate.localeCompare(leftDate)
    return dateOrder || left.sessionId.localeCompare(right.sessionId)
  })
}

export function reconcilePdfChatSelection(
  selectedIds: ReadonlySet<string>,
  chats: readonly PdfRecentChat[],
): Set<string> {
  const currentIds = new Set(chats.map((chat) => chat.id))
  return new Set(
    Array.from(selectedIds).filter((sessionId) => currentIds.has(sessionId)),
  )
}
