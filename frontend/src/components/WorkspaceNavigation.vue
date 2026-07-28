<script setup lang="ts">
import type { WorkspaceNavigationItem } from '../types/workspace-navigation'
import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    items: WorkspaceNavigationItem[]
    variant?: 'primary' | 'rail'
    ariaLabel?: string
  }>(),
  {
    variant: 'primary',
    ariaLabel: 'Workspace navigation',
  },
)

const emit = defineEmits<{
  select: [itemId: string]
}>()
</script>

<template>
  <nav
    :class="variant === 'primary' ? 'primary-nav' : 'rail-system-links'"
    :aria-label="ariaLabel"
  >
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      :class="{
        'nav-item': variant === 'primary',
        active: item.active,
        'muted-nav': item.disabled,
      }"
      :disabled="item.disabled"
      :aria-current="item.active ? 'page' : undefined"
      :aria-disabled="item.disabled ? 'true' : undefined"
      @click="emit('select', item.id)"
    >
      <span v-if="variant === 'primary'" class="nav-glyph">
        <AppIcon :name="item.icon" />
      </span>
      <AppIcon v-else :name="item.icon" />
      <span>{{ item.label }}</span>
    </button>
  </nav>
</template>
