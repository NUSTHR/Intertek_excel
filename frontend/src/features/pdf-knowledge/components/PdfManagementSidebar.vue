<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import WorkspaceNavigation from '../../../components/WorkspaceNavigation.vue'
import type { PdfManagementNavItem, PdfWorkspaceMode } from '../types'

defineProps<{
  isAdmin: boolean
  navItems: PdfManagementNavItem[]
  isUploading: boolean
  userEmail: string
  userRoleLabel: string
}>()

const emit = defineEmits<{
  changeMode: [mode: PdfWorkspaceMode]
  openDiagnostics: []
  requestUpload: []
  logout: []
}>()

function handleNavClick(itemId: string): void {
  if (itemId === 'chat') {
    emit('changeMode', 'chat')
  } else if (itemId === 'diagnostics') {
    emit('openDiagnostics')
  }
}
</script>

<template>
  <aside class="pdfmgmt-sidebar app-sidebar" aria-label="PDF knowledge management navigation">
    <div class="pdfmgmt-brand brand-block">
      <h1>PDF AI</h1>
      <p>Researcher Pro</p>
    </div>

    <button
      v-if="isAdmin"
      type="button"
      class="pdfmgmt-upload-primary sidebar-upload-button"
      :disabled="isUploading"
      @click="emit('requestUpload')"
    >
      <AppIcon name="add" />
      <span>Upload Folder</span>
    </button>

    <WorkspaceNavigation
      :items="navItems"
      aria-label="PDF library navigation"
      @select="handleNavClick"
    />

    <div class="pdfmgmt-sidebar-footer sidebar-footer">
      <button type="button" class="pdfmgmt-support nav-item muted-nav support-link" disabled>
        <span class="nav-glyph"><AppIcon name="help" /></span>
        <span>Support</span>
      </button>
      <div class="pdfmgmt-user-card user-mini">
        <div class="pdfmgmt-avatar avatar" :class="{ admin: isAdmin }" aria-hidden="true">
          <AppIcon :name="isAdmin ? 'verified' : 'user'" />
        </div>
        <div>
          <strong>{{ userRoleLabel }}</strong>
          <span>{{ userEmail }}</span>
        </div>
        <button type="button" class="logout-button" aria-label="Logout" @click="emit('logout')">
          <AppIcon name="logout" />
        </button>
      </div>
    </div>
  </aside>
</template>
