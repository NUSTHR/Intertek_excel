<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { ActionMenuItem } from '../action-menu-contract'
import { useOutsideClose } from '../composables/use-outside-close'

const props = withDefaults(defineProps<{
  isOpen: boolean
  items: ActionMenuItem[]
  triggerLabel: string
  anchor?: 'left' | 'right'
  disabled?: boolean
  rootClass?: string
  triggerClass?: string
  menuClass?: string
}>(), {
  anchor: 'right',
  disabled: false,
  rootClass: '',
  triggerClass: '',
  menuClass: '',
})

const emit = defineEmits<{
  toggle: []
  select: [actionId: string]
  close: []
}>()

const containerRef = ref<HTMLElement | null>(null)
const isOpen = computed(() => props.isOpen)

useOutsideClose({
  isOpen,
  containerRef,
  onClose: () => emit('close'),
})

function selectItem(item: ActionMenuItem): void {
  if (props.disabled || item.disabled) {
    return
  }
  emit('select', item.id)
}
</script>

<template>
  <span ref="containerRef" class="base-action-menu-control" :class="rootClass">
    <button
      type="button"
      :class="triggerClass"
      :disabled="disabled"
      :aria-label="triggerLabel"
      :aria-expanded="isOpen"
      aria-haspopup="menu"
      @click.stop="emit('toggle')"
    >
      <AppIcon name="more_vert" />
    </button>

    <span
      v-if="isOpen"
      class="file-workspace-base-action-menu"
      :class="menuClass"
      :data-anchor="anchor"
      :aria-disabled="disabled"
      role="menu"
    >
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        class="file-workspace-base-action-menu-item"
        :data-tone="item.tone ?? 'default'"
        :disabled="disabled || item.disabled"
        role="menuitem"
        @click="selectItem(item)"
      >
        <AppIcon :name="item.iconName" />
        <span>{{ item.label }}</span>
      </button>
    </span>
  </span>
</template>
