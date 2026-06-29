<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { PdfManagementNavItem, PdfWorkspaceMode } from '../types'

defineProps<{
  navItems: PdfManagementNavItem[]
  isUploading: boolean
}>()

const emit = defineEmits<{
  changeMode: [mode: PdfWorkspaceMode]
  requestUpload: []
}>()

function handleNavClick(itemId: string): void {
  if (itemId === 'chat') {
    emit('changeMode', 'chat')
  }
}
</script>

<template>
  <aside class="pdfmgmt-sidebar" aria-label="PDF knowledge management navigation">
    <div class="pdfmgmt-brand">
      <h1>ExcelAI</h1>
      <p>Researcher Pro</p>
    </div>

    <button
      type="button"
      class="pdfmgmt-upload-primary"
      :disabled="isUploading"
      @click="emit('requestUpload')"
    >
      <AppIcon name="add" />
      <span>Upload New</span>
    </button>

    <nav class="pdfmgmt-nav" aria-label="Management sections">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="pdfmgmt-nav-item"
        :class="{ active: item.active }"
        @click="handleNavClick(item.id)"
      >
        <AppIcon :name="item.icon" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="pdfmgmt-sidebar-footer">
      <button type="button" class="pdfmgmt-support" disabled>
        <AppIcon name="help" />
        <span>Support</span>
      </button>
      <div class="pdfmgmt-user-card">
        <div class="pdfmgmt-avatar" aria-hidden="true">AI</div>
        <div>
          <strong>PDF Workspace</strong>
          <span>Knowledge tools</span>
        </div>
        <button type="button" aria-label="Logout unavailable" disabled>
          <AppIcon name="logout" />
        </button>
      </div>
    </div>
  </aside>
</template>
