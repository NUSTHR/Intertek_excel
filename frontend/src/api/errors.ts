import { getAuthToken, getCsrfToken } from './auth-token'
import { publishSessionExpired } from './session-events'

export interface ApiErrorPayload {
  detail?: string
  requires_confirmation?: boolean
  retry_after_seconds?: number
}

export class ExcelWorkspaceApiError extends Error {
  readonly statusCode: number | null
  readonly requiresConfirmation: boolean
  readonly retryAfterSeconds: number | null

  constructor(
    message: string,
    statusCode: number | null = null,
    requiresConfirmation = false,
    retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'ExcelWorkspaceApiError'
    this.statusCode = statusCode
    this.requiresConfirmation = requiresConfirmation
    this.retryAfterSeconds = retryAfterSeconds
  }
}

export interface RequestOptions {
  apiBaseUrl?: string
  abortMessage?: string
  signal?: AbortSignal
  suppressSessionExpiredEvent?: boolean
  timeoutMs?: number
  timeoutMessage?: string
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const response = await request(path, init, options)
  return (await response.json()) as T
}

export async function requestEmpty(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<void> {
  await request(path, init, options)
}

async function request(
  path: string,
  init: RequestInit,
  options: RequestOptions,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? 30000
  const externalSignal = options.signal ?? init.signal ?? null
  let cancelledByCaller = false

  const abortFromCaller = () => {
    cancelledByCaller = true
    controller.abort()
  }
  if (externalSignal?.aborted) {
    abortFromCaller()
  } else {
    externalSignal?.addEventListener('abort', abortFromCaller, { once: true })
  }

  const timeoutId = window.setTimeout(() => {
    controller.abort()
  }, timeoutMs)
  try {
    const response = await fetch(`${options.apiBaseUrl ?? ''}${path}`, {
      ...init,
      headers: buildHeaders(init.headers),
      credentials: init.credentials ?? 'include',
      signal: controller.signal,
    })
    if (!response.ok) {
      const payload = await parseErrorPayload(response)
      if (response.status === 401 && !options.suppressSessionExpiredEvent) {
        publishSessionExpired()
      }
      throw new ExcelWorkspaceApiError(
        payload.detail || `Request failed with status ${response.status}.`,
        response.status,
        payload.requires_confirmation === true,
        typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null,
      )
    }
    return response
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError) {
      throw error
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ExcelWorkspaceApiError(
        cancelledByCaller
          ? (options.abortMessage ?? 'Request cancelled.')
          : (options.timeoutMessage ?? 'Request timed out.'),
      )
    }
    if (error instanceof TypeError) {
      throw new ExcelWorkspaceApiError(
        'Unable to reach the workspace backend. Check whether it is running.',
      )
    }
    if (error instanceof Error) {
      throw new ExcelWorkspaceApiError(error.message)
    }
    throw new ExcelWorkspaceApiError('Network error. Check whether the workspace backend is running.')
  } finally {
    window.clearTimeout(timeoutId)
    externalSignal?.removeEventListener('abort', abortFromCaller)
  }
}

function buildHeaders(headers: HeadersInit | undefined): HeadersInit {
  const nextHeaders = new Headers(headers)
  const token = getAuthToken()
  if (token && !nextHeaders.has('Authorization')) {
    nextHeaders.set('Authorization', `Bearer ${token}`)
  }
  const csrfToken = getCsrfToken()
  if (csrfToken && !nextHeaders.has('X-CSRF-Token')) {
    nextHeaders.set('X-CSRF-Token', csrfToken)
  }
  return nextHeaders
}

async function parseErrorPayload(response: Response): Promise<ApiErrorPayload> {
  const text = await response.text()
  if (!text) {
    return {}
  }
  try {
    return JSON.parse(text) as ApiErrorPayload
  } catch {
    return { detail: text }
  }
}
