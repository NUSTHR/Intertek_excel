<script setup lang="ts">
import type { WorkspaceNavigationItem } from '../types/workspace-navigation'
import AppIcon from './AppIcon.vue'

withDefaults(
  defineProps<{
    items: WorkspaceNavigationItem[]
    variant?: 'primary' | 'rail' | 'global'
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
    :class="{
      'primary-nav': variant === 'primary',
      'rail-system-links': variant === 'rail',
      'workspace-global-nav': variant === 'global',
    }"
    :aria-label="ariaLabel"
  >
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      :class="{
        'nav-item': variant === 'primary',
        'workspace-global-nav__item': variant === 'global',
        active: item.active,
        'muted-nav': item.disabled,
      }"
      :disabled="item.disabled"
      :title="item.label"
      :aria-current="item.active ? 'page' : undefined"
      :aria-disabled="item.disabled ? 'true' : undefined"
      @click="emit('select', item.id)"
    >
      <span v-if="variant === 'primary'" class="nav-glyph">
        <AppIcon :name="item.icon" />
      </span>
      <span v-else-if="variant === 'global'" class="workspace-global-nav__icon">
        <AppIcon :name="item.icon" />
      </span>
      <AppIcon v-else :name="item.icon" />
      <span :class="variant === 'global' ? 'workspace-global-nav__label' : 'workspace-nav-text'">
        {{ item.label }}
      </span>
    </button>
  </nav>
</template>
