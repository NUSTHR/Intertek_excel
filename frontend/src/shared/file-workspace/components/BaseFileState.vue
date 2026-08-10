<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { FileDomain, FileWorkspaceIconName } from '../file-card-contract'

withDefaults(defineProps<{
  domain: FileDomain
  tone?: 'empty' | 'loading' | 'error'
  iconName: FileWorkspaceIconName
  title: string
  detail?: string
}>(), {
  tone: 'empty',
  detail: '',
})
</script>

<template>
  <div
    class="file-workspace-base-state"
    :data-domain="domain"
    :data-tone="tone"
    :role="tone === 'error' ? 'alert' : 'status'"
  >
    <span class="file-workspace-base-state-icon" aria-hidden="true">
      <AppIcon :name="iconName" />
    </span>
    <strong>{{ title }}</strong>
    <span v-if="detail">{{ detail }}</span>
  </div>
</template>
