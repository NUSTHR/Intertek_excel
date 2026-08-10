<script setup lang="ts">
import { ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { FileWorkspaceIconName } from '../file-card-contract'

const props = withDefaults(defineProps<{
  title: string
  iconName: FileWorkspaceIconName
  meta?: string
  collapsible?: boolean
  defaultOpen?: boolean
  tone?: 'default' | 'premium'
}>(), {
  meta: '',
  collapsible: false,
  defaultOpen: true,
  tone: 'default',
})

const isOpen = ref(props.defaultOpen)
</script>

<template>
  <section class="file-workspace-base-card" :data-tone="tone">
    <header class="file-workspace-base-card-head">
      <button
        v-if="collapsible"
        type="button"
        class="file-workspace-base-card-title file-workspace-base-card-toggle"
        :aria-expanded="isOpen"
        @click="isOpen = !isOpen"
      >
        <AppIcon :name="iconName" />
        <strong>{{ title }}</strong>
        <AppIcon name="keyboard_arrow_down" class="file-workspace-base-card-chevron" :class="{ open: isOpen }" />
      </button>
      <span v-else class="file-workspace-base-card-title">
        <AppIcon :name="iconName" />
        <strong>{{ title }}</strong>
      </span>
      <small v-if="meta">{{ meta }}</small>
      <span class="file-workspace-base-card-actions"><slot name="actions"></slot></span>
    </header>
    <div v-if="isOpen" class="file-workspace-base-card-body">
      <slot></slot>
    </div>
  </section>
</template>
