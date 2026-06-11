import type { AuthResponse, AuthUser, PasswordResetResponse } from '../types/auth'
import { requestEmpty, requestJson } from './errors'

const apiBaseUrl = import.meta.env.VITE_EXCEL_WORKSPACE_API_BASE_URL ?? ''
const requestTimeoutMs = Number(
  import.meta.env.VITE_EXCEL_WORKSPACE_REQUEST_TIMEOUT_MS ?? 30000,
)

const requestOptions = {
  apiBaseUrl,
  timeoutMs: requestTimeoutMs,
}

export async function register(email: string, password: string): Promise<AuthResponse> {
  return requestJson<AuthResponse>(
    '/api/auth/register',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    },
    requestOptions,
  )
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return requestJson<AuthResponse>(
    '/api/auth/login',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    },
    requestOptions,
  )
}

export async function getCurrentUser(): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/me', { method: 'GET' }, requestOptions)
}

export async function logout(): Promise<void> {
  return requestEmpty('/api/auth/logout', { method: 'POST' }, requestOptions)
}

export async function requestPasswordReset(
  email: string,
): Promise<PasswordResetResponse> {
  return requestJson<PasswordResetResponse>(
    '/api/auth/password/forgot',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    },
    requestOptions,
  )
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<AuthResponse> {
  return requestJson<AuthResponse>(
    '/api/auth/password/reset',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ token, new_password: newPassword }),
    },
    requestOptions,
  )
}
