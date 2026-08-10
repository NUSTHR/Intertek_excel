<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { useOutsideClose } from '../composables/use-outside-close'
import type {
  BaseFileActionMenuEmits,
  BaseFileActionMenuProps,
  FileActionItem,
} from '../file-action-menu-contract'

const props = defineProps<BaseFileActionMenuProps>()

const emit = defineEmits<BaseFileActionMenuEmits>()

const containerRef = ref<HTMLElement | null>(null)
const isOpenLocal = computed(() => props.isOpen)

useOutsideClose({
  isOpen: isOpenLocal,
  containerRef,
  internalSelector: '[data-file-action-menu-item]',
  onClose: () => emit('close'),
})

function selectItem(item: FileActionItem): void {
  if (props.isDisabled || item.disabled) {
    return
  }
  emit('select', item.id)
}
</script>

<template>
  <span
    v-if="isOpen"
    ref="containerRef"
    class="file-workspace-base-action-menu"
    :data-anchor="anchor"
    :aria-disabled="isDisabled"
    role="menu"
  >
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      class="file-workspace-base-action-menu-item"
      :data-tone="item.tone ?? 'default'"
      data-file-action-menu-item
      :disabled="isDisabled || item.disabled"
      role="menuitem"
      @click="selectItem(item)"
    >
      <AppIcon :name="item.iconName" />
      <span>{{ item.label }}</span>
    </button>
  </span>
</template>
