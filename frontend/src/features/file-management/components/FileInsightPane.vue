<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceInsightPane from '../../../components/file-workspace/FileWorkspaceInsightPane.vue'

import type { FileInsightTab } from '../../../app/workspace-types'

const tabs: Array<{ key: FileInsightTab; label: string }> = [
  { key: 'summary', label: 'Summary' },
  { key: 'preview', label: 'Data Preview' },
  { key: 'schema', label: 'Schema' },
]

defineProps<{
  activeTab: FileInsightTab
  fullscreen: boolean
  canDownloadPreview: boolean
}>()

const emit = defineEmits<{
  changeTab: [tab: FileInsightTab]
  downloadPreview: []
  toggleFullscreen: []
}>()
</script>

<template>
  <FileWorkspaceInsightPane domain="excel" :fullscreen="fullscreen">
    <template #tabs>
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        :class="{ active: activeTab === tab.key }"
        :aria-pressed="activeTab === tab.key"
        @click="emit('changeTab', tab.key)"
      >
        {{ tab.label }}
      </button>
    </template>

    <template #actions>
        <button
          type="button"
          class="icon-only-button"
          aria-label="Download preview"
          :disabled="!canDownloadPreview"
          @click="emit('downloadPreview')"
        >
          <AppIcon name="download" />
        </button>
        <button
          type="button"
          class="icon-only-button"
          :aria-label="fullscreen ? 'Exit fullscreen' : 'Fullscreen'"
          @click="emit('toggleFullscreen')"
        >
          <AppIcon :name="fullscreen ? 'fullscreen_exit' : 'fullscreen'" />
        </button>
    </template>

    <slot v-if="activeTab === 'summary'" name="summary"></slot>
    <slot v-else-if="activeTab === 'preview'" name="preview"></slot>
    <slot v-else name="schema"></slot>
  </FileWorkspaceInsightPane>
</template>
