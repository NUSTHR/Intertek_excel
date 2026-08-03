import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { getCurrentUser, logout as logoutSession } from '../../api/auth-api'
import { clearAuthToken } from '../../api/auth-token'
import { ExcelWorkspaceApiError } from '../../api/excel-assets-api'
import { subscribeToSessionExpired } from '../../api/session-events'
import type { AuthResponse, AuthUser } from '../../types/auth'
import { toErrorMessage } from '../workspace-utils'

interface UseAuthSessionOptions {
  initializeWorkspace: () => Promise<void>
  resetWorkspaceState: () => Promise<void>
}

export function useAuthSession(options: UseAuthSessionOptions) {
  const currentUser = ref<AuthUser | null>(null)
  const isAuthChecking = ref<boolean>(true)
  const authErrorMessage = ref<string>('')
  let unsubscribeFromSessionExpired: (() => void) | null = null

  const isAdmin = computed(() => currentUser.value?.role === 'admin')
  const userEmail = computed(() => currentUser.value?.email ?? '')
  const userRoleLabel = computed(() => (isAdmin.value ? 'Administrator' : 'Workspace user'))

  async function restoreAuthentication(): Promise<void> {
    authErrorMessage.value = ''
    isAuthChecking.value = true
    try {
      currentUser.value = await getCurrentUser()
    } catch (error: unknown) {
      clearAuthToken()
      currentUser.value = null
      authErrorMessage.value =
        error instanceof ExcelWorkspaceApiError && error.statusCode === 401
          ? ''
          : toErrorMessage(error)
    } finally {
      isAuthChecking.value = false
    }
    if (currentUser.value) {
      await options.initializeWorkspace()
    }
  }

  function handleSessionExpired(): void {
    if (!currentUser.value) {
      return
    }
    clearAuthToken()
    currentUser.value = null
    authErrorMessage.value = 'Your session has expired. Please sign in again.'
    void options.resetWorkspaceState()
  }

  async function handleAuthenticated(response: AuthResponse): Promise<void> {
    clearAuthToken()
    currentUser.value = response.user
    authErrorMessage.value = ''
    await options.resetWorkspaceState()
    await options.initializeWorkspace()
  }

  async function signOut(): Promise<void> {
    try {
      await logoutSession()
    } catch {
      // Local state cleanup remains the fallback if the server session is already gone.
    }
    clearAuthToken()
    currentUser.value = null
    await options.resetWorkspaceState()
  }

  onMounted(() => {
    unsubscribeFromSessionExpired = subscribeToSessionExpired(handleSessionExpired)
    void restoreAuthentication()
  })

  onBeforeUnmount(() => {
    unsubscribeFromSessionExpired?.()
    unsubscribeFromSessionExpired = null
  })

  return {
    authErrorMessage,
    currentUser,
    handleAuthenticated,
    isAdmin,
    isAuthChecking,
    signOut,
    userEmail,
    userRoleLabel,
  }
}
