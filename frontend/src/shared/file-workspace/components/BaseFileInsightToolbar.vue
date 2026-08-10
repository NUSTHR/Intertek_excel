<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type {
  BaseFileInsightToolbarEmits,
  BaseFileInsightToolbarProps,
} from '../file-insight-toolbar-contract'

const props = defineProps<BaseFileInsightToolbarProps>()

const emit = defineEmits<BaseFileInsightToolbarEmits>()
</script>

<template>
  <div class="file-workspace-base-insight-toolbar" role="toolbar" aria-label="Insight actions">
    <button
      v-if="showDownloadPreview"
      type="button"
      class="icon-only-button"
      :disabled="!canDownloadPreview || isDownloading"
      :aria-label="downloadLabel"
      :title="downloadLabel"
      @click="emit('downloadPreview')"
    >
      <AppIcon name="download" />
    </button>
    <button
      v-if="showFullscreen"
      type="button"
      class="icon-only-button"
      :disabled="isTogglingFullscreen"
      :aria-label="fullscreenLabel"
      :title="fullscreenLabel"
      :data-active="isFullscreen"
      @click="emit('toggleFullscreen')"
    >
      <AppIcon :name="isFullscreen ? 'fullscreen_exit' : 'fullscreen'" />
    </button>
  </div>
</template>
