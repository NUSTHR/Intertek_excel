<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceInsightPane from '../../../components/file-workspace/FileWorkspaceInsightPane.vue'
import BaseFileInsightTabs from '../../../shared/file-workspace/components/BaseFileInsightTabs.vue'
import BaseFileInsightToolbar from '../../../shared/file-workspace/components/BaseFileInsightToolbar.vue'
import BaseModelConfiguration from '../../../shared/file-workspace/components/BaseModelConfiguration.vue'
import BaseDocumentSummaryCard from '../../../shared/file-workspace/components/BaseDocumentSummaryCard.vue'
import BaseInsightSectionCard from '../../../shared/file-workspace/components/BaseInsightSectionCard.vue'
import BaseFileState from '../../../shared/file-workspace/components/BaseFileState.vue'
import type { BaseModelStageViewModel } from '../../../shared/file-workspace/model-configuration-contract'
import { fileWorkspaceCopy, summaryEmptyCopy } from '../../../shared/file-workspace/copy'
import type {
  PdfDocumentPreviewBlock,
  PdfDocumentSchemaItem,
  PdfDocumentSummary,
  PdfManagedFile,
  PdfManagementInsightTab,
  PdfModelSetting,
  PdfModelSettingFieldErrors,
} from '../types'

const props = defineProps<{
  isAdmin: boolean
  activeTab: PdfManagementInsightTab
  contextTags: string[]
  modelSettings: PdfModelSetting[]
  modelSettingErrors: Record<string, PdfModelSettingFieldErrors>
  selectedFile?: PdfManagedFile
  selectedFiles: PdfManagedFile[]
  summary: PdfDocumentSummary | null
  previewBlocks: PdfDocumentPreviewBlock[]
  schema: PdfDocumentSchemaItem[]
  isDetailLoading: boolean
  isSummaryGenerating: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  tabChange: [tab: PdfManagementInsightTab]
  generateSummary: []
  modelSettingChange: [
    settingId: string,
    field: 'selectedProvider' | 'selectedModel',
    value: string,
  ]
}>()

const isFullscreen = ref(false)
const tabs: Array<{ key: PdfManagementInsightTab; label: string }> = [
  { key: 'summary', label: fileWorkspaceCopy.tabs.summary },
  { key: 'preview', label: fileWorkspaceCopy.tabs.preview },
  { key: 'schema', label: fileWorkspaceCopy.tabs.schema },
]
const summaryEmpty = computed(() => summaryEmptyCopy('pdf', selectedCount.value > 0))
const selectedCount = computed(() => props.selectedFiles.length)
const selectedFolderCount = computed(
  () => props.selectedFiles.filter((file) => file.kind === 'folder').length,
)
const canGenerateSummary = computed(() => selectedCount.value > 0)
const isBatchSummarySelection = computed(
  () => selectedCount.value > 1 || selectedFolderCount.value > 0,
)
const selectionSummaryLabel = computed(() => {
  if (selectedCount.value === 0) {
    return ''
  }
  if (selectedCount.value === 1) {
    const selected = props.selectedFiles[0]
    return selected.kind === 'folder'
      ? `Selected folder: ${selected.name}`
      : `Selected file: ${selected.name}`
  }
  return `${selectedCount.value} sources selected`
})
const generateSummaryLabel = computed(() => {
  if (props.isSummaryGenerating) {
    return isBatchSummarySelection.value ? 'Queueing...' : 'Generating...'
  }
  if (isBatchSummarySelection.value) {
    return 'Generate Summaries'
  }
  return props.summary?.status === 'ready' ? 'Regenerate' : 'Generate Summary'
})
const generateSummaryIcon = computed<'refresh' | 'bolt'>(() => (
  props.summary?.status === 'ready' ? 'refresh' : 'bolt'
))
const summaryTags = computed(() => Array.from(new Set([
  ...(props.summary?.keyTopics ?? []),
  ...props.contextTags,
])))
const routingSignals = computed(() => Array.from(new Set([
  ...(props.summary?.positiveRoutingTerms ?? []),
  ...(props.summary?.exactIdentifiers ?? []),
  ...(props.summary?.negativeRoutingTerms ?? []),
])))
const modelSettingError = (
  settingId: string,
  field: keyof PdfModelSettingFieldErrors,
): string => props.modelSettingErrors[settingId]?.[field] ?? ''
const normalizedModelStages = computed<BaseModelStageViewModel[]>(() => props.modelSettings.map((setting) => ({
  id: setting.id,
  label: setting.label.replace(/Engine$/, 'Model'),
  provider: setting.selectedProvider,
  model: setting.selectedModel,
  providers: setting.providers.map((provider) => ({
    value: provider,
    label: providerLabel(provider),
  })),
  models: (setting.providerModels?.[setting.selectedProvider] ?? []).map((model) => ({
    value: model,
    label: model,
  })),
  errorMessage: modelSettingError(setting.id, 'selectedProvider')
    || modelSettingError(setting.id, 'selectedModel'),
})))
const providerLabels: Record<string, string> = {
  deepseek: 'DeepSeek Official',
  siliconflow: 'SiliconFlow',
  volcengine_ark: 'Volcengine Ark',
}

function providerLabel(provider: string): string {
  return providerLabels[provider] ?? provider
}

function handleModelSettingChange(
  settingId: string,
  field: 'provider' | 'model',
  value: string,
): void {
  emit(
    'modelSettingChange',
    settingId,
    field === 'provider' ? 'selectedProvider' : 'selectedModel',
    value,
  )
}
</script>

<template>
  <FileWorkspaceInsightPane domain="pdf" :fullscreen="isFullscreen">
    <template #tabs>
      <BaseFileInsightTabs
        :active-tab="activeTab"
        :tabs="tabs"
        @change="emit('tabChange', $event)"
      />
    </template>

    <template #actions>
      <BaseFileInsightToolbar
        :show-download-preview="false"
        show-fullscreen
        :can-download-preview="false"
        :is-fullscreen="isFullscreen"
        :is-downloading="false"
        :is-toggling-fullscreen="false"
        download-label="Download preview"
        :fullscreen-label="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
        @toggle-fullscreen="isFullscreen = !isFullscreen"
      />
    </template>

      <section v-if="activeTab === 'summary'" class="file-summary-stack">
        <BaseModelConfiguration
          v-if="modelSettings.length > 0"
          :stages="normalizedModelStages"
          :disabled="!isAdmin"
          @change="handleModelSettingChange"
        />

        <BaseDocumentSummaryCard
          :subtitle="selectionSummaryLabel"
          :action-label="generateSummaryLabel"
          :action-icon="generateSummaryIcon"
          :action-disabled="!canGenerateSummary || isSummaryGenerating"
          @generate="emit('generateSummary')"
        >
          <p v-if="errorMessage" class="pdfmgmt-inline-error">{{ errorMessage }}</p>

          <div
            v-if="!isBatchSummarySelection && summary?.status === 'ready'"
            class="summary-view-layout"
          >
            <section class="summary-main-panel">
              <div class="summary-section-head">
                <div><span>Summary</span></div>
              </div>
              <div class="summary-scroll-panel summary-text-panel">
                <p>{{ summary.content }}</p>
                <small v-if="summary.updatedLabel">Updated {{ summary.updatedLabel }}</small>
              </div>
            </section>

            <aside class="summary-side-panel">
              <section class="summary-tags-panel">
                <div class="summary-section-head">
                  <div>
                    <span>Keywords &amp; Tags</span>
                    <strong>{{ summaryTags.length }}</strong>
                  </div>
                </div>
                <div class="summary-scroll-panel summary-tag-scroll">
                  <span v-for="tag in summaryTags" :key="tag" class="summary-tag-pill">
                    #{{ tag }}
                  </span>
                  <span v-if="summaryTags.length === 0" class="summary-placeholder">
                    No tags yet.
                  </span>
                </div>
              </section>

              <section class="summary-routing-panel">
                <div class="summary-section-head compact"><span>Routing Signals</span></div>
                <div class="summary-scroll-panel summary-routing-scroll">
                  <span v-for="signal in routingSignals" :key="signal">{{ signal }}</span>
                  <span v-if="routingSignals.length === 0" class="summary-placeholder">
                    No routing signals yet.
                  </span>
                </div>
              </section>
            </aside>
          </div>

          <div v-else class="insight-empty-state document-summary-empty">
            <div class="insight-icon"><AppIcon name="auto_awesome" /></div>
            <h4>{{ isDetailLoading ? 'Loading document insight' : summaryEmpty.title }}</h4>
            <p>
              {{
                isSummaryGenerating
                  ? isBatchSummarySelection
                    ? 'Summary tasks are being queued for the selected files.'
                    : 'The summary model is reading the selected file.'
                  : isBatchSummarySelection
                    ? 'Generate summaries for every PDF contained in the selected files or folders.'
                    : summaryEmpty.detail
              }}
            </p>
            <button
              type="button"
              class="summary-action-button primary file-workspace-base-primary-action"
              :disabled="!canGenerateSummary || isSummaryGenerating"
              @click="emit('generateSummary')"
            >
              <AppIcon name="bolt" />
              {{ generateSummaryLabel }}
            </button>
          </div>
        </BaseDocumentSummaryCard>
      </section>

      <BaseInsightSectionCard
        v-else-if="activeTab === 'preview'"
        title="Data Preview"
        icon-name="description"
        :meta="`${previewBlocks.length} blocks`"
        tone="premium"
      >
        <div class="pdfmgmt-preview-list">
          <article v-for="block in previewBlocks" :key="block.id" class="pdfmgmt-preview-block">
            <span>{{ block.pageLabel }}</span>
            <strong>{{ block.title }}</strong>
            <p>{{ block.content }}</p>
          </article>
          <BaseFileState
            v-if="previewBlocks.length === 0"
            domain="pdf"
            icon-name="description"
            title="No preview available"
            detail="Preview content will appear after parsing is complete."
          />
        </div>
      </BaseInsightSectionCard>

      <BaseInsightSectionCard
        v-else
        title="Schema"
        icon-name="schema"
        :meta="`${schema.length} fields`"
        tone="premium"
      >
        <div class="pdfmgmt-schema-grid">
          <div v-for="item in schema" :key="item.id">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
          <BaseFileState
            v-if="schema.length === 0"
            domain="pdf"
            icon-name="schema"
            title="No schema extracted"
            detail="Extracted metadata and index statistics will appear here."
          />
        </div>
      </BaseInsightSectionCard>
  </FileWorkspaceInsightPane>
</template>
