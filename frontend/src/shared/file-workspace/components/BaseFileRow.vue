<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { FileActionId, BaseFileRowViewModel } from '../file-card-contract'
import type { FileActionItem } from '../file-action-menu-contract'
import BaseFileActionMenu from './BaseFileActionMenu.vue'

const props = withDefaults(defineProps<{
  model: BaseFileRowViewModel
  actions?: FileActionItem[]
  menuOpen?: boolean
  disabled?: boolean
}>(), {
  actions: () => [],
  menuOpen: false,
  disabled: false,
})

const emit = defineEmits<{
  select: [model: BaseFileRowViewModel]
  toggleCheck: [model: BaseFileRowViewModel]
  openFolder: [model: BaseFileRowViewModel]
  toggleMenu: [model: BaseFileRowViewModel]
  requestAction: [model: BaseFileRowViewModel, action: FileActionId]
  closeMenu: []
}>()
</script>

<template>
  <article
    class="file-workspace-base-row"
    :data-domain="model.domain"
    :data-kind="model.kind"
    :data-state="model.isSelected ? 'selected' : 'default'"
    :data-progress="model.isProgressing"
    role="listitem"
  >
    <input
      v-if="model.isMultiSelectable"
      class="file-workspace-base-row-check"
      type="checkbox"
      :checked="model.isChecked"
      :disabled="disabled"
      :aria-label="`Select ${model.displayName}`"
      @click.stop
      @change="emit('toggleCheck', model)"
    />

    <button
      type="button"
      class="file-workspace-base-row-main"
      :disabled="disabled"
      :aria-label="`Select ${model.displayName}`"
      @click="emit('select', model)"
    >
      <span class="file-workspace-base-row-icon" aria-hidden="true">
        <AppIcon :name="model.iconName" />
      </span>
      <span class="file-workspace-base-row-copy">
        <strong :title="model.displayName">{{ model.displayName }}</strong>
        <span class="file-workspace-base-row-meta">
          <template v-for="(part, index) in model.metaParts" :key="`${part}-${index}`">
            <span v-if="index > 0" aria-hidden="true">·</span>
            <span>{{ part }}</span>
          </template>
        </span>
        <span v-if="model.visibilityChip" class="file-workspace-base-row-chip">
          <AppIcon name="visibility_off" />
          {{ model.visibilityChip }}
        </span>
        <span
          v-if="model.isProgressing"
          class="file-workspace-base-progress"
          role="progressbar"
          :aria-label="`${model.displayName} progress`"
          :aria-valuenow="model.progressPercent"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <span :style="{ width: `${model.progressPercent}%` }"></span>
        </span>
      </span>
    </button>

    <span v-if="model.isPinned" class="file-workspace-base-row-pin" title="Pinned">
      <AppIcon name="push_pin" />
    </span>

    <span v-if="actions.length > 0" class="file-workspace-base-row-actions">
      <button
        type="button"
        class="file-workspace-base-menu-trigger"
        :disabled="disabled"
        :aria-label="`Actions for ${model.displayName}`"
        :aria-expanded="menuOpen"
        aria-haspopup="menu"
        data-file-action-menu-item
        @click.stop="emit('toggleMenu', model)"
      >
        <AppIcon name="more_vert" />
      </button>
      <BaseFileActionMenu
        :is-open="menuOpen"
        :items="actions"
        anchor="right"
        :is-disabled="disabled"
        @select="emit('closeMenu'); emit('requestAction', model, $event)"
        @close="emit('closeMenu')"
      />
    </span>

    <button
      v-if="model.isFolderOpenable"
      type="button"
      class="file-workspace-base-folder-open"
      :disabled="disabled"
      :aria-label="`Open folder ${model.displayName}`"
      @click.stop="emit('openFolder', model)"
    >
      <AppIcon name="chevron_right" />
    </button>
  </article>
</template>
