<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import FileWorkspaceInsightPane from '../../../components/file-workspace/FileWorkspaceInsightPane.vue'
import type {
  PdfDocumentPreviewBlock,
  PdfDocumentSchemaItem,
  PdfDocumentSummary,
  PdfManagedFile,
  PdfManagementInsightTab,
  PdfModelSetting,
  PdfModelSettingFieldErrors,
  PdfSummaryTask,
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
  summaryTasks: PdfSummaryTask[]
  previewBlocks: PdfDocumentPreviewBlock[]
  schema: PdfDocumentSchemaItem[]
  isDetailLoading: boolean
  isSummaryGenerating: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  tabChange: [tab: PdfManagementInsightTab]
  generateSummary: []
  cancelSummaryTask: [taskId: string]
  retrySummaryTask: [taskId: string]
  modelSettingChange: [
    settingId: string,
    field: 'selectedProvider' | 'selectedModel',
    value: string,
  ]
}>()

const isModelConfigOpen = ref(true)
const isSummaryOpen = ref(true)
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
    return 'No sources selected'
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
const generateSummaryIcon = computed(() => (props.summary?.status === 'ready' ? 'refresh' : 'bolt'))
const modelSettingError = (
  settingId: string,
  field: keyof PdfModelSettingFieldErrors,
): string => props.modelSettingErrors[settingId]?.[field] ?? ''
const hasModelSettingError = (settingId: string): boolean =>
  Boolean(
    modelSettingError(settingId, 'selectedProvider') ||
      modelSettingError(settingId, 'selectedModel'),
  )
const isModelSupported = (setting: PdfModelSetting, model: string): boolean =>
  setting.providerModels?.[setting.selectedProvider]?.includes(model) ?? false
const summaryTaskResultLabel = computed(() => {
  const tasks = props.summaryTasks
  if (tasks.length === 0) {
    return ''
  }
  const readyCount = tasks.filter((task) => task.status === 'ready').length
  const skippedCount = tasks.filter((task) => task.status === 'skipped').length
  const failedCount = tasks.filter((task) =>
    ['failed', 'cancelled'].includes(task.status),
  ).length
  const completedCount = readyCount + skippedCount
  const activeCount = tasks.length - completedCount - failedCount
  if (activeCount > 0) {
    return `${completedCount} of ${tasks.length} summary tasks completed.`
  }
  if (failedCount > 0) {
    return `${completedCount} completed; ${failedCount} failed or cancelled.`
  }
  return `${completedCount} summary task${completedCount === 1 ? '' : 's'} completed.`
})

const providerLabels: Record<string, string> = {
  deepseek: 'DeepSeek Official',
  siliconflow: 'SiliconFlow',
  volcengine_ark: 'Volcengine Ark',
}

function providerLabel(provider: string): string {
  return providerLabels[provider] ?? provider
}

function canCancelSummaryTask(task: PdfSummaryTask): boolean {
  return task.status === 'queued' || task.status === 'running'
}

function canRetrySummaryTask(task: PdfSummaryTask): boolean {
  return task.status === 'failed' || task.status === 'cancelled'
}
</script>

<template>
  <FileWorkspaceInsightPane domain="pdf">
    <template #tabs>
        <button
          type="button"
          :class="{ active: activeTab === 'summary' }"
          @click="emit('tabChange', 'summary')"
        >
          Summary
        </button>
        <button
          type="button"
          :class="{ active: activeTab === 'preview' }"
          @click="emit('tabChange', 'preview')"
        >
          Data Preview
        </button>
        <button
          type="button"
          :class="{ active: activeTab === 'schema' }"
          @click="emit('tabChange', 'schema')"
        >
          Schema
        </button>
    </template>

    <template #actions>
      <div class="pdfmgmt-insight-actions">
        <button
          type="button"
          class="icon-only-button"
          aria-label="Download unavailable"
          disabled
        >
          <AppIcon name="download" />
        </button>
        <button
          type="button"
          class="icon-only-button"
          aria-label="Fullscreen unavailable"
          disabled
        >
          <AppIcon name="fullscreen" />
        </button>
      </div>
    </template>

      <section class="pdfmgmt-panel">
        <button
          type="button"
          class="pdfmgmt-panel-header"
          :aria-expanded="isModelConfigOpen"
          @click="isModelConfigOpen = !isModelConfigOpen"
        >
          <span>
            <AppIcon name="tune" />
            <strong>Model Configuration</strong>
          </span>
          <AppIcon
            name="keyboard_arrow_down"
            class="pdfmgmt-panel-chevron"
            :class="{ open: isModelConfigOpen }"
          />
        </button>

        <div v-if="isModelConfigOpen" class="pdfmgmt-model-grid">
          <div v-for="setting in modelSettings" :key="setting.id" class="pdfmgmt-model-row">
            <label>{{ setting.label }}</label>
            <div class="pdfmgmt-model-control">
              <select
                :value="setting.selectedProvider"
                aria-label="Provider"
                :aria-invalid="hasModelSettingError(setting.id)"
                :class="{ 'pdfmgmt-field-invalid': hasModelSettingError(setting.id) }"
                :disabled="!isAdmin"
                @change="
                  emit(
                    'modelSettingChange',
                    setting.id,
                    'selectedProvider',
                    ($event.target as HTMLSelectElement).value,
                  )
                "
              >
                <option v-for="provider in setting.providers" :key="provider" :value="provider">
                  {{ providerLabel(provider) }}
                </option>
              </select>
            </div>
            <div class="pdfmgmt-model-control">
              <select
                :value="setting.selectedModel"
                aria-label="Model"
                :aria-invalid="hasModelSettingError(setting.id)"
                :class="{ 'pdfmgmt-field-invalid': hasModelSettingError(setting.id) }"
                :disabled="!isAdmin"
                @change="
                  emit(
                    'modelSettingChange',
                    setting.id,
                    'selectedModel',
                    ($event.target as HTMLSelectElement).value,
                  )
                "
              >
                <option
                  v-for="model in setting.models"
                  :key="model"
                  :disabled="!isModelSupported(setting, model)"
                >
                  {{ model }}
                </option>
              </select>
            </div>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'summary'" class="pdfmgmt-panel premium">
        <div class="pdfmgmt-panel-header split">
          <button
            type="button"
            class="pdfmgmt-panel-title-button"
            :aria-expanded="isSummaryOpen"
            @click="isSummaryOpen = !isSummaryOpen"
          >
            <span>
              <AppIcon name="auto_awesome" />
              <strong>AI Executive Summary</strong>
              <AppIcon
                name="keyboard_arrow_down"
                class="pdfmgmt-panel-chevron"
                :class="{ open: isSummaryOpen }"
              />
            </span>
          </button>
          <span class="pdfmgmt-summary-actions">
            <button
              type="button"
              :disabled="!canGenerateSummary || isSummaryGenerating"
              @click="emit('generateSummary')"
            >
              <AppIcon :name="generateSummaryIcon" />
              {{ generateSummaryLabel }}
            </button>
            <button type="button" aria-label="Edit summary unavailable" disabled>
              <AppIcon name="edit" />
            </button>
          </span>
        </div>

        <div v-if="isSummaryOpen" class="pdfmgmt-summary-body">
          <p v-if="errorMessage" class="pdfmgmt-inline-error">{{ errorMessage }}</p>
          <p class="pdfmgmt-selection-summary">{{ selectionSummaryLabel }}</p>

          <div v-if="!isBatchSummarySelection && summary?.status === 'ready'" class="pdfmgmt-ready-summary">
            <span>
              <AppIcon name="auto_awesome" />
            </span>
            <p>{{ summary.content }}</p>
            <small>{{ summary.updatedLabel }}</small>
          </div>

          <div v-else class="pdfmgmt-empty-summary">
            <span>
              <AppIcon name="auto_awesome" />
            </span>
            <strong>{{ isDetailLoading ? 'Loading document insight' : 'No summary generated' }}</strong>
            <p>
              {{
                isSummaryGenerating
                  ? isBatchSummarySelection
                    ? 'Summary tasks are being queued for the selected sources.'
                    : 'The summary engine is reading the selected source.'
                  : isBatchSummarySelection
                    ? 'Generate summaries for every PDF contained in the selected files or folders.'
                    : 'Select a data source from the left and click generate to reveal deep AI insights and patterns.'
              }}
            </p>
            <p v-if="summaryTasks.length > 0" class="pdfmgmt-summary-task-result">
              {{ summaryTaskResultLabel }}
            </p>
            <div v-if="summaryTasks.length > 0" class="pdfmgmt-summary-task-list">
              <div
                v-for="task in summaryTasks"
                :key="task.id"
                class="pdfmgmt-task-card compact"
              >
                <span>
                  <strong>{{ task.detail || `Summary ${task.status}` }}</strong>
                  <span>{{ task.status }} · {{ task.progress }}%</span>
                  <small v-if="task.errorMessage">{{ task.errorMessage }}</small>
                </span>
                <span v-if="isAdmin" class="pdfmgmt-task-actions">
                  <button
                    v-if="canCancelSummaryTask(task)"
                    type="button"
                    @click="emit('cancelSummaryTask', task.id)"
                  >
                    Cancel
                  </button>
                  <button
                    v-if="canRetrySummaryTask(task)"
                    type="button"
                    @click="emit('retrySummaryTask', task.id)"
                  >
                    Retry
                  </button>
                </span>
              </div>
            </div>
            <button
              type="button"
              class="pdfmgmt-summary-primary-action"
              :disabled="!canGenerateSummary || isSummaryGenerating"
              @click="emit('generateSummary')"
            >
              <AppIcon name="bolt" />
              {{ generateSummaryLabel }}
            </button>
          </div>

          <div class="pdfmgmt-tags">
            <div>
              <span>Contextual Tags</span>
              <button type="button" disabled>
                <AppIcon name="add" />
                Add Tag
              </button>
            </div>
            <div class="pdfmgmt-tag-list">
              <span v-for="tag in contextTags" :key="tag">
                {{ tag }}
                <AppIcon name="close" />
              </span>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'preview'" class="pdfmgmt-panel premium">
        <div class="pdfmgmt-panel-static-header">
          <span>
            <AppIcon name="description" />
            <strong>Data Preview</strong>
          </span>
          <small>{{ previewBlocks.length }} blocks</small>
        </div>
        <div class="pdfmgmt-preview-list">
          <article v-for="block in previewBlocks" :key="block.id" class="pdfmgmt-preview-block">
            <span>{{ block.pageLabel }}</span>
            <strong>{{ block.title }}</strong>
            <p>{{ block.content }}</p>
          </article>
          <div v-if="previewBlocks.length === 0" class="pdfmgmt-empty-summary compact">
            <span>
              <AppIcon name="description" />
            </span>
            <strong>No preview blocks</strong>
            <p>Preview content will appear after parsing is complete.</p>
          </div>
        </div>
      </section>

      <section v-else class="pdfmgmt-panel premium">
        <div class="pdfmgmt-panel-static-header">
          <span>
            <AppIcon name="schema" />
            <strong>Schema</strong>
          </span>
          <small>{{ schema.length }} fields</small>
        </div>
        <div class="pdfmgmt-schema-grid">
          <div v-for="item in schema" :key="item.id">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
          <div v-if="schema.length === 0" class="pdfmgmt-empty-summary compact">
            <span>
              <AppIcon name="schema" />
            </span>
            <strong>No schema extracted</strong>
            <p>MinerU metadata and index statistics will appear here.</p>
          </div>
        </div>
      </section>
  </FileWorkspaceInsightPane>
</template>
