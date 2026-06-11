import type {
  ChatAnswer,
  ChatModelSelection,
  ChatRouteResult,
  ChatSession,
  ChatSessionListResponse,
  ChatTurn,
  ChatTurnListResponse,
} from '../types/chat'
import { requestEmpty, requestJson } from './errors'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''
const requestTimeoutMs = Number(import.meta.env.VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS ?? 180000)

const requestOptions = {
  apiBaseUrl,
  timeoutMs: requestTimeoutMs,
  timeoutMessage: 'Chat request timed out while waiting for the model.',
}

export async function createChatSession(): Promise<ChatSession> {
  return requestJson<ChatSession>(
    '/api/excel/chat/sessions',
    { method: 'POST' },
    requestOptions,
  )
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const payload = await requestJson<ChatSessionListResponse>(
    '/api/excel/chat/sessions',
    { method: 'GET' },
    requestOptions,
  )
  return payload.sessions
}

export async function listChatSessionTurns(sessionId: string): Promise<ChatTurn[]> {
  const payload = await requestJson<ChatTurnListResponse>(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/turns`,
    { method: 'GET' },
    requestOptions,
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
    requestOptions,
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
    requestOptions,
  )
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return requestEmpty(
    `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'DELETE',
    },
    requestOptions,
  )
}

export async function askExcelQuestion(
  question: string,
  sessionId: string | null = null,
  modelSelection: ChatModelSelection | null = null,
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
        router_model: modelSelection?.routerModel ?? null,
        router_provider: modelSelection?.routerProvider ?? null,
        answer_model: modelSelection?.answerModel ?? null,
        answer_provider: modelSelection?.answerProvider ?? null,
        enable_deep_thinking: modelSelection?.enableDeepThinking ?? false,
      }),
    },
    requestOptions,
  )
}

export async function routeExcelQuestion(
  question: string,
  sessionId: string,
  routerModel: string | null = null,
  routerProvider: string | null = null,
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
        router_model: routerModel,
        router_provider: routerProvider,
      }),
    },
    requestOptions,
  )
}

export async function answerRoutedExcelQuestion(
  question: string,
  sessionId: string,
  answerModel: string | null = null,
  answerProvider: string | null = null,
  selectedVersionIds: string[] = [],
  enableDeepThinking = false,
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
        answer_model: answerModel,
        answer_provider: answerProvider,
        selected_version_ids: selectedVersionIds,
        enable_deep_thinking: enableDeepThinking,
      }),
    },
    requestOptions,
  )
}
