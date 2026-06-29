<script setup lang="ts">
import { ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type {
  PdfDocumentPreviewBlock,
  PdfDocumentSchemaItem,
  PdfDocumentSummary,
  PdfManagedFile,
  PdfManagementInsightTab,
  PdfModelSetting,
} from '../types'

defineProps<{
  activeTab: PdfManagementInsightTab
  contextTags: string[]
  modelSettings: PdfModelSetting[]
  selectedFile?: PdfManagedFile
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

const isModelConfigOpen = ref(true)
const isSummaryOpen = ref(true)
</script>

<template>
  <section class="pdfmgmt-insight-pane">
    <header class="pdfmgmt-insight-tabs">
      <div>
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
      </div>
      <div class="pdfmgmt-insight-actions">
        <button type="button" aria-label="Download unavailable" disabled>
          <AppIcon name="download" />
        </button>
        <button type="button" aria-label="Fullscreen unavailable" disabled>
          <AppIcon name="fullscreen" />
        </button>
      </div>
    </header>

    <div class="pdfmgmt-insight-scroll">
      <section v-if="selectedFile" class="pdfmgmt-selected-source">
        <span class="pdfmgmt-selected-source-icon" :class="selectedFile.kind">
          <AppIcon :name="selectedFile.kind === 'folder' ? 'folder_open' : 'description'" />
        </span>
        <div>
          <span>Active Source</span>
          <strong>{{ selectedFile.name }}</strong>
        </div>
        <small>{{ selectedFile.statusDetail }}</small>
      </section>

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
            <select
              :value="setting.selectedProvider"
              aria-label="Provider"
              @change="
                emit(
                  'modelSettingChange',
                  setting.id,
                  'selectedProvider',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option v-for="provider in setting.providers" :key="provider">
                {{ provider }}
              </option>
            </select>
            <select
              :value="setting.selectedModel"
              aria-label="Model"
              @change="
                emit(
                  'modelSettingChange',
                  setting.id,
                  'selectedModel',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option v-for="model in setting.models" :key="model">
                {{ model }}
              </option>
            </select>
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
              :disabled="!selectedFile || isSummaryGenerating"
              @click="emit('generateSummary')"
            >
              <AppIcon name="refresh" />
              {{ isSummaryGenerating ? 'Generating' : 'Regenerate' }}
            </button>
            <button type="button" aria-label="Edit summary unavailable" disabled>
              <AppIcon name="edit" />
            </button>
          </span>
        </div>

        <div v-if="isSummaryOpen" class="pdfmgmt-summary-body">
          <p v-if="errorMessage" class="pdfmgmt-inline-error">{{ errorMessage }}</p>

          <div v-if="summary?.status === 'ready'" class="pdfmgmt-ready-summary">
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
                  ? 'The summary engine is reading the selected source.'
                  : 'Select a data source from the left and click generate to reveal deep AI insights and patterns.'
              }}
            </p>
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
    </div>
  </section>
</template>
