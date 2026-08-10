<script setup lang="ts">
import FileWorkspaceInsightPane from '../../../components/file-workspace/FileWorkspaceInsightPane.vue'
import BaseFileInsightTabs from '../../../shared/file-workspace/components/BaseFileInsightTabs.vue'
import BaseFileInsightToolbar from '../../../shared/file-workspace/components/BaseFileInsightToolbar.vue'
import { fileWorkspaceCopy } from '../../../shared/file-workspace/copy'

import type { FileInsightTab } from '../../../app/workspace-types'

const tabs: Array<{ key: FileInsightTab; label: string }> = [
  { key: 'summary', label: fileWorkspaceCopy.tabs.summary },
  { key: 'preview', label: fileWorkspaceCopy.tabs.preview },
  { key: 'schema', label: fileWorkspaceCopy.tabs.schema },
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
      <BaseFileInsightTabs
        :active-tab="activeTab"
        :tabs="tabs"
        @change="emit('changeTab', $event)"
      />
    </template>

    <template #actions>
      <BaseFileInsightToolbar
        show-download-preview
        show-fullscreen
        :can-download-preview="canDownloadPreview"
        :is-fullscreen="fullscreen"
        :is-downloading="false"
        :is-toggling-fullscreen="false"
        download-label="Download preview"
        :fullscreen-label="fullscreen ? 'Exit fullscreen' : 'Fullscreen'"
        @download-preview="emit('downloadPreview')"
        @toggle-fullscreen="emit('toggleFullscreen')"
      />
    </template>

    <slot v-if="activeTab === 'summary'" name="summary"></slot>
    <slot v-else-if="activeTab === 'preview'" name="preview"></slot>
    <slot v-else name="schema"></slot>
  </FileWorkspaceInsightPane>
</template>
