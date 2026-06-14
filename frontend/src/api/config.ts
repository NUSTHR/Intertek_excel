import type { RequestOptions } from './errors'

const defaultRequestTimeoutMs = readNumberEnv(
  import.meta.env.VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS,
  30000,
)

const chatRequestTimeoutMs = readNumberEnv(
  import.meta.env.VITE_EXCEL_WORKSPACE_CHAT_TIMEOUT_MS,
  240000,
)

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''

export const defaultRequestOptions: RequestOptions = {
  apiBaseUrl,
  timeoutMs: defaultRequestTimeoutMs,
}

export const chatRequestOptions: RequestOptions = {
  apiBaseUrl,
  timeoutMs: chatRequestTimeoutMs,
  timeoutMessage: 'Chat request timed out while waiting for the model.',
}

function readNumberEnv(value: string | undefined, fallback: number): number {
  if (value === undefined || value.trim() === '') {
    return fallback
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}
