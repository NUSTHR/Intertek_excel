import { ref } from 'vue'

const workspaceSidebarStorageKey = 'knowledgeai-workspace-sidebar-collapsed'
const compactViewportQuery = '(max-width: 760px)'

function readInitialCollapsedState(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    const storedPreference = window.localStorage.getItem(workspaceSidebarStorageKey)
    if (storedPreference !== null) {
      return storedPreference === 'true'
    }
  } catch {
    // Storage can be unavailable in private or embedded browser contexts.
  }
  return window.matchMedia(compactViewportQuery).matches
}

function persistCollapsedState(collapsed: boolean): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.localStorage.setItem(workspaceSidebarStorageKey, String(collapsed))
  } catch {
    // A persisted preference is optional; sidebar interaction must keep working.
  }
}

export function useWorkspaceSidebar() {
  const isSidebarCollapsed = ref(readInitialCollapsedState())

  function toggleSidebar(): void {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
    persistCollapsedState(isSidebarCollapsed.value)
  }

  return {
    isSidebarCollapsed,
    toggleSidebar,
  }
}
