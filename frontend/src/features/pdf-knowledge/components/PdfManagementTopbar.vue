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
  <header class="pdfmgmt-topbar">
    <label class="pdfmgmt-search">
      <AppIcon name="search" />
      <input
        type="search"
        placeholder="Search knowledge base..."
        :value="searchTerm"
        @input="emit('searchTermChange', ($event.target as HTMLInputElement).value)"
      />
    </label>

    <div class="pdfmgmt-topbar-meta">
      <strong>Knowledge Interface</strong>
      <span></span>
      <button type="button" aria-label="Notifications unavailable" disabled>
        <AppIcon name="notifications" />
      </button>
      <button type="button" aria-label="History unavailable" disabled>
        <AppIcon name="refresh" />
      </button>
      <div class="pdfmgmt-topbar-avatar" :class="{ admin: isAdmin }" aria-hidden="true">
        <AppIcon :name="isAdmin ? 'verified' : 'user'" />
      </div>
    </div>
  </header>
</template>
