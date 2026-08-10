import { ref } from 'vue'

export function useWorkspaceSidebar() {
  // A fresh application load always starts from the compact navigation rail.
  // The state remains interactive for the lifetime of the current Vue app, but
  // is deliberately not persisted across full page loads.
  const isSidebarCollapsed = ref(true)

  function toggleSidebar(): void {
    isSidebarCollapsed.value = !isSidebarCollapsed.value
  }

  return {
    isSidebarCollapsed,
    toggleSidebar,
  }
}
