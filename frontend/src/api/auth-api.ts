import type { AuthResponse, AuthUser, PasswordResetResponse } from '../types/auth'
import { defaultRequestOptions } from './config'
import { requestEmpty, requestJson } from './errors'

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
    defaultRequestOptions,
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
    defaultRequestOptions,
  )
}

export async function getCurrentUser(): Promise<AuthUser> {
  return requestJson<AuthUser>('/api/auth/me', { method: 'GET' }, defaultRequestOptions)
}

export async function logout(): Promise<void> {
  return requestEmpty('/api/auth/logout', { method: 'POST' }, defaultRequestOptions)
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
    defaultRequestOptions,
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
    defaultRequestOptions,
  )
}
