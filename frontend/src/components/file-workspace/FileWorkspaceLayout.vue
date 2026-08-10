<script setup lang="ts">
import AppIcon from '../AppIcon.vue'

defineProps<{
  domain: 'excel' | 'pdf'
  title: string
  searchTerm: string
  searchLabel: string
  searchPlaceholder: string
  isAdmin: boolean
}>()

const emit = defineEmits<{
  searchTermChange: [value: string]
}>()
</script>

<template>
  <section class="file-workspace-layout" :data-file-domain="domain" :data-domain="domain">
    <header class="file-workspace-topbar topbar file-topbar">
      <label class="search-field file-search-field">
        <span class="search-icon"><AppIcon name="search" /></span>
        <input
          type="search"
          :aria-label="searchLabel"
          :placeholder="searchPlaceholder"
          :value="searchTerm"
          @input="emit('searchTermChange', ($event.target as HTMLInputElement).value)"
        />
      </label>

      <div class="file-topbar-meta">
        <strong class="workspace-topbar-title">{{ title }}</strong>
        <span class="topbar-divider"></span>
        <slot name="actions"></slot>
        <div class="topbar-avatar" :class="{ admin: isAdmin }" aria-hidden="true">
          <AppIcon :name="isAdmin ? 'verified' : 'user'" />
        </div>
      </div>
    </header>

    <div class="file-workspace-content">
      <section class="file-workspace-source-pane file-sources-pane">
        <slot name="source"></slot>
      </section>
      <section class="file-workspace-insight-pane">
        <slot name="insight"></slot>
      </section>
    </div>
    <slot name="overlay"></slot>
  </section>
</template>
