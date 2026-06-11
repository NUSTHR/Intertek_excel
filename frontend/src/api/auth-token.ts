const authTokenStorageKey = 'excelai-auth-token'

let inMemoryAuthToken = loadStoredAuthToken()

export function getAuthToken(): string {
  return inMemoryAuthToken
}

export function setAuthToken(token: string): void {
  inMemoryAuthToken = token
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(authTokenStorageKey, token)
  }
}

export function clearAuthToken(): void {
  inMemoryAuthToken = ''
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(authTokenStorageKey)
  }
}

function loadStoredAuthToken(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return window.localStorage.getItem(authTokenStorageKey) ?? ''
}
