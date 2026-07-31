import type {
  ChatAnswer,
  ChatModelSelection,
  ChatRouteResult,
  ChatSession,
  ChatSessionListResponse,
  ChatTurn,
  ChatTurnListResponse,
} from '../types/chat'
import { chatRequestOptions } from './config'
import { requestEmpty, requestJson } from './errors'

export async function createChatSession(): Promise<ChatSession> {
  return requestJson<ChatSession>(
    '/api/excel/chat/sessions',
    { method: 'POST' },
    chatRequestOptions,
  )
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const payload = await requestJson<ChatSessionListResponse>(
    '/api/excel/chat/sessions',
    { method: 'GET' },
    chatRequestOptions,
  )
  return payload.sessions
}

export async function listChatSessionTurns(sessionId: string): Promise<ChatTurn[]> {
  const payload = await requestJson<ChatTurnListResponse>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/turns`,
    { method: 'GET' },
    chatRequestOptions,
  )
  return payload.turns
}

export async function renameChatSession(sessionId: string, title: string): Promise<ChatSession> {
  return requestJson<ChatSession>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title }),
    },
    chatRequestOptions,
  )
}

export async function setChatSessionPinned(
  sessionId: string,
  pinned: boolean,
): Promise<ChatSession> {
  return requestJson<ChatSession>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/pin`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ pinned }),
    },
    chatRequestOptions,
  )
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return requestEmpty(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'DELETE',
    },
    chatRequestOptions,
  )
}

export async function askExcelQuestion(
  question: string,
  sessionId: string | null = null,
  modelSelection: ChatModelSelection | null = null,
  requestOptions: { requestId?: string; signal?: AbortSignal } = {},
): Promise<ChatAnswer> {
  const path = sessionId
    ? `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/messages`
    : '/api/excel/chat'
  return requestJson<ChatAnswer>(
    path,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        enable_deep_thinking: modelSelection?.enableDeepThinking ?? false,
        request_id: requestOptions.requestId ?? null,
      }),
    },
    {
      ...chatRequestOptions,
      abortMessage: 'Chat request cancelled.',
      signal: requestOptions.signal,
    },
  )
}

export async function cancelChatRequest(requestId: string): Promise<void> {
  await requestJson<{ request_id: string; cancelled: boolean }>(
    '/api/excel/chat/cancel',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ request_id: requestId }),
    },
    chatRequestOptions,
  )
}

export async function routeExcelQuestion(
  question: string,
  sessionId: string,
  requestId: string | null = null,
): Promise<ChatRouteResult> {
  return requestJson<ChatRouteResult>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/route`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        request_id: requestId,
      }),
    },
    chatRequestOptions,
  )
}

export async function answerRoutedExcelQuestion(
  question: string,
  sessionId: string,
  selectedVersionIds: string[] = [],
  enableDeepThinking = false,
  requestOptions: {
    requestId?: string
    sessionRevision?: number
    signal?: AbortSignal
  } = {},
): Promise<ChatAnswer> {
  return requestJson<ChatAnswer>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/answer`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        question,
        selected_version_ids: selectedVersionIds,
        session_revision: requestOptions.sessionRevision ?? null,
        enable_deep_thinking: enableDeepThinking,
        request_id: requestOptions.requestId ?? null,
      }),
    },
    {
      ...chatRequestOptions,
      abortMessage: 'Chat request cancelled.',
      signal: requestOptions.signal,
    },
  )
}
