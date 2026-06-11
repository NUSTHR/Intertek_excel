export interface ApiErrorPayload {
  detail?: string
  requires_confirmation?: boolean
}

export class ExcelWorkspaceApiError extends Error {
  readonly statusCode: number | null
  readonly requiresConfirmation: boolean

  constructor(
    message: string,
    statusCode: number | null = null,
    requiresConfirmation = false,
  ) {
    super(message)
    this.name = 'ExcelWorkspaceApiError'
    this.statusCode = statusCode
    this.requiresConfirmation = requiresConfirmation
  }
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options: {
    apiBaseUrl?: string
    timeoutMs?: number
    timeoutMessage?: string
  } = {},
): Promise<T> {
  const response = await request(path, init, options)
  return (await response.json()) as T
}

export async function requestEmpty(
  path: string,
  init: RequestInit = {},
  options: {
    apiBaseUrl?: string
    timeoutMs?: number
    timeoutMessage?: string
  } = {},
): Promise<void> {
  await request(path, init, options)
}

async function request(
  path: string,
  init: RequestInit,
  options: {
    apiBaseUrl?: string
    timeoutMs?: number
    timeoutMessage?: string
  },
): Promise<Response> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? 30000
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${options.apiBaseUrl ?? ''}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
    })
    if (!response.ok) {
      const payload = await parseErrorPayload(response)
      throw new ExcelWorkspaceApiError(
        payload.detail || `Request failed with status ${response.status}.`,
        response.status,
        payload.requires_confirmation === true,
      )
    }
    return response
  } catch (error: unknown) {
    if (error instanceof ExcelWorkspaceApiError) {
      throw error
    }
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ExcelWorkspaceApiError(options.timeoutMessage ?? 'Request timed out.')
    }
    if (error instanceof TypeError) {
      throw new ExcelWorkspaceApiError(
        'Unable to reach the Excel backend. Check whether it is running.',
      )
    }
    if (error instanceof Error) {
      throw new ExcelWorkspaceApiError(error.message)
    }
    throw new ExcelWorkspaceApiError('Network error. Check whether the Excel backend is running.')
  } finally {
    window.clearTimeout(timeoutId)
  }
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
