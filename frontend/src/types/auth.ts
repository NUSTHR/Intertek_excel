export type UserRole = 'admin' | 'member'

export interface AuthUser {
  user_id: string
  email: string
  role: UserRole
  created_at: string
  last_login_at: string | null
}

export interface AuthResponse {
  user: AuthUser
  access_token: string
  token_type: 'bearer'
  expires_at: string
}

export interface PasswordResetResponse {
  email: string
  reset_token: string | null
  expires_at: string | null
}
