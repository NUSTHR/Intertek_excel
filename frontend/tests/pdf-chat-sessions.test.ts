import assert from 'node:assert/strict'
import test from 'node:test'

import type {
  PdfChatSession,
  PdfRecentChat,
} from '../src/features/pdf-knowledge/types.ts'
import {
  reconcilePdfChatSelection,
  sortPdfChatSessions,
} from '../src/features/pdf-knowledge/utils/pdf-chat-sessions.ts'

function session(
  sessionId: string,
  updatedAt: string,
  pinnedAt?: string,
): PdfChatSession {
  return {
    sessionId,
    userId: 'user-1',
    title: sessionId,
    pinnedAt,
    status: 'active',
    createdAt: updatedAt,
    updatedAt,
    contextFileIds: [],
    revision: 0,
  }
}

test('sorts pinned PDF chats first and applies deterministic time ordering', () => {
  const sessions = sortPdfChatSessions([
    session('older', '2026-01-01T00:00:00Z'),
    session('pinned-older', '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z'),
    session('newer', '2026-01-04T00:00:00Z'),
    session('pinned-newer', '2026-01-01T00:00:00Z', '2026-01-05T00:00:00Z'),
  ])

  assert.deepEqual(
    sessions.map((item) => item.sessionId),
    ['pinned-newer', 'pinned-older', 'newer', 'older'],
  )
})

test('reconciles batch selection with the current PDF chat list', () => {
  const chats: PdfRecentChat[] = [
    {
      id: 'kept',
      title: 'Kept',
      updatedAt: '2026-01-01T00:00:00Z',
      revision: 1,
    },
  ]

  assert.deepEqual(
    Array.from(reconcilePdfChatSelection(new Set(['kept', 'removed']), chats)),
    ['kept'],
  )
})
