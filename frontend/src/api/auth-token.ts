const csrfCookieName = 'excelai_csrf'
let inMemoryAuthToken = ''

export function getAuthToken(): string {
  return inMemoryAuthToken
}

export function setAuthToken(token: string): void {
  inMemoryAuthToken = token
}

export function clearAuthToken(): void {
  inMemoryAuthToken = ''
}

export function getCsrfToken(): string {
  if (typeof document === 'undefined') {
    return ''
  }
  const cookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${csrfCookieName}=`))
  if (!cookie) {
    return ''
  }
  return decodeURIComponent(cookie.slice(csrfCookieName.length + 1))
}
