<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import { fileWorkspaceCopy } from '../copy'

import {
  type BaseFilePaginationEmits,
  type BaseFilePaginationViewModel,
} from '../file-pagination-contract'

defineProps<{
  model: BaseFilePaginationViewModel
}>()

const emit = defineEmits<BaseFilePaginationEmits>()
</script>

<template>
  <nav
    v-if="model.pageCount > 0"
    class="file-workspace-base-pagination"
    aria-label="File pagination"
  >
    <span class="file-workspace-base-pagination-label">{{ model.paginationLabel }}</span>

    <div
      v-if="model.showNavigation"
      class="file-workspace-base-pagination-controls"
    >
      <button
        type="button"
        class="file-workspace-base-pagination-button file-workspace-base-pagination-direction"
        :disabled="!model.canGoPrevious"
        @click="emit('stepPage', -1)"
      >
        <AppIcon name="chevron_left" />
        <span>{{ fileWorkspaceCopy.actions.previous }}</span>
      </button>

      <div class="file-workspace-base-pagination-pages">
        <template v-for="item in model.items" :key="item.kind === 'page' ? item.page : item.key">
          <span
            v-if="item.kind === 'ellipsis'"
            class="file-workspace-base-pagination-ellipsis"
            aria-hidden="true"
          >…</span>
          <span
            v-else-if="item.isCurrent"
            class="file-workspace-base-pagination-button"
            data-active="true"
            aria-current="page"
          >{{ item.page }}</span>
          <button
            v-else
            type="button"
            class="file-workspace-base-pagination-button"
            @click="emit('setPage', item.page)"
          >{{ item.page }}</button>
        </template>
      </div>

      <button
        type="button"
        class="file-workspace-base-pagination-button file-workspace-base-pagination-direction"
        :disabled="!model.canGoNext"
        @click="emit('stepPage', 1)"
      >
        <span>{{ fileWorkspaceCopy.actions.next }}</span>
        <AppIcon name="chevron_right" />
      </button>
    </div>

    <span class="file-workspace-base-pagination-balance" aria-hidden="true"></span>
  </nav>
</template>
