<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'

defineProps<{
  isAdmin: boolean
  searchTerm: string
}>()

const emit = defineEmits<{
  searchTermChange: [value: string]
}>()
</script>

<template>
  <header class="pdfmgmt-topbar topbar file-topbar">
    <label class="pdfmgmt-search search-field file-search-field">
      <span class="search-icon"><AppIcon name="search" /></span>
      <input
        type="search"
        placeholder="Search knowledge base..."
        :value="searchTerm"
        @input="emit('searchTermChange', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <div class="pdfmgmt-topbar-meta file-topbar-meta">
      <strong>PDF Workspace</strong>
      <span class="topbar-divider"></span>
      <button
        type="button"
        class="topbar-icon-button"
        aria-label="Notifications unavailable"
        disabled
      >
        <AppIcon name="notifications" />
      </button>
      <button
        type="button"
        class="topbar-icon-button"
        aria-label="History unavailable"
        disabled
      >
        <AppIcon name="refresh" />
      </button>
      <div
        class="pdfmgmt-topbar-avatar topbar-avatar"
        :class="{ admin: isAdmin }"
        aria-hidden="true"
      >
        <AppIcon :name="isAdmin ? 'verified' : 'user'" />
      </div>
    </div>
  </header>
</template>
