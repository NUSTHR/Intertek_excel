import type {
  ChatAnswer,
  ChatModelSelection,
  ChatRouteResult,
  ChatSession,
  ChatSessionListResponse,
  ChatTurn,
  ChatTurnListResponse,
} from '../types/chat'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''
const requestTimeoutMs = Number(import.meta.env.VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS ?? 180000)

interface ChatErrorPayload {
  detail?: string
}

export async function createChatSession(): Promise<ChatSession> {
  const response = await fetch(`${apiBaseUrl}/api/excel/chat/sessions`, {
    method: 'POST',
  })
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as ChatSession
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const response = await fetch(`${apiBaseUrl}/api/excel/chat/sessions`)
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  const payload = (await response.json()) as ChatSessionListResponse
  return payload.sessions
}

export async function listChatSessionTurns(sessionId: string): Promise<ChatTurn[]> {
  const response = await fetch(
    `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/turns`,
  )
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  const payload = (await response.json()) as ChatTurnListResponse
  return payload.turns
}

export async function renameChatSession(sessionId: string, title: string): Promise<ChatSession> {
  const response = await fetch(
    `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ title }),
    },
  )
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as ChatSession
}

export async function setChatSessionPinned(
  sessionId: string,
  pinned: boolean,
): Promise<ChatSession> {
  const response = await fetch(
    `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/pin`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ pinned }),
    },
  )
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as ChatSession
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await fetch(
    `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: 'DELETE',
    },
  )
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
}

export async function askExcelQuestion(
  question: string,
  sessionId: string | null = null,
  modelSelection: ChatModelSelection | null = null,
): Promise<ChatAnswer> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs)
  const path = sessionId
    ? `/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/messages`
    : '/api/excel/chat'
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
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
      }),
      signal: controller.signal,
    })
    if (!response.ok) {
      const payload = await parseErrorPayload(response)
      throw new Error(payload.detail || `Request failed with status ${response.status}.`)
    }
    return (await response.json()) as ChatAnswer
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Chat request timed out while waiting for the model.')
    }
    if (error instanceof Error) {
      throw error
    }
    throw new Error('Unexpected chat request error.')
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export async function routeExcelQuestion(
  question: string,
  sessionId: string,
  routerModel: string | null = null,
  routerProvider: string | null = null,
): Promise<ChatRouteResult> {
  const response = await fetch(
    `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/route`,
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
  )
  if (!response.ok) {
    const payload = await parseErrorPayload(response)
    throw new Error(payload.detail || `Request failed with status ${response.status}.`)
  }
  return (await response.json()) as ChatRouteResult
}

export async function answerRoutedExcelQuestion(
  question: string,
  sessionId: string,
  answerModel: string | null = null,
  answerProvider: string | null = null,
  selectedVersionIds: string[] = [],
): Promise<ChatAnswer> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), requestTimeoutMs)
  try {
    const response = await fetch(
      `${apiBaseUrl}/api/excel/chat/sessions/${encodeURIComponent(sessionId)}/answer`,
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
        }),
        signal: controller.signal,
      },
    )
    if (!response.ok) {
      const payload = await parseErrorPayload(response)
      throw new Error(payload.detail || `Request failed with status ${response.status}.`)
    }
    return (await response.json()) as ChatAnswer
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Chat request timed out while waiting for the model.')
    }
    if (error instanceof Error) {
      throw error
    }
    throw new Error('Unexpected chat request error.')
  } finally {
    window.clearTimeout(timeoutId)
  }
}

async function parseErrorPayload(response: Response): Promise<ChatErrorPayload> {
  const text = await response.text()
  if (!text) {
    return {}
  }
  try {
    return JSON.parse(text) as ChatErrorPayload
  } catch {
    return { detail: text }
  }
}
