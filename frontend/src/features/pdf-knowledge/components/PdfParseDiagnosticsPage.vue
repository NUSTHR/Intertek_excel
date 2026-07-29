<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import {
  getPdfDocumentDetail,
  getPdfUploadTask,
  listPdfParserProfiles,
  listPdfKnowledgeFiles,
  reparsePdfDocument,
  updatePdfParserProfile,
} from '../../../api/pdf-knowledge-api'
import AppIcon from '../../../components/AppIcon.vue'
import type {
  PdfDocumentDetail,
  PdfManagedFile,
  PdfParseReport,
  PdfParserProfile,
  PdfUploadTask,
} from '../types'
import { usePdfTaskPolling } from '../composables/use-pdf-task-polling'

const props = defineProps<{
  isAdmin: boolean
}>()

const emit = defineEmits<{
  openPdfWorkspace: []
}>()

const reparseTaskPolling = usePdfTaskPolling()
const diagnosticPageSize = 25
const files = ref<PdfManagedFile[]>([])
const filePage = ref(1)
const selectedFileId = ref<string>('')
const detail = ref<PdfDocumentDetail | null>(null)
const isLoadingFiles = ref(false)
const isLoadingDetail = ref(false)
const isLoadingProfiles = ref(false)
const isReparsing = ref(false)
const isUpdatingProfile = ref(false)
const reparsingFileId = ref('')
const reparseTasksByFileId = ref<Record<string, PdfUploadTask>>({})
const filesError = ref('')
const detailError = ref('')
const profilesError = ref('')
const reparseError = ref('')
const parserProfiles = ref<PdfParserProfile[]>([])
const selectedParserProfileId = ref('')
let detailRequestId = 0

const pdfFiles = computed(() => {
  return files.value.filter((file) => file.kind === 'pdf')
})

const filePageCount = computed(() => (
  Math.max(1, Math.ceil(pdfFiles.value.length / diagnosticPageSize))
))

const paginatedPdfFiles = computed(() => {
  const normalizedPage = Math.min(filePage.value, filePageCount.value)
  const start = (normalizedPage - 1) * diagnosticPageSize
  return pdfFiles.value.slice(start, start + diagnosticPageSize)
})

const selectedFile = computed(() => {
  return pdfFiles.value.find((file) => file.id === selectedFileId.value)
})

const fileLookup = computed(() => {
  return new Map(files.value.map((file) => [file.id, file]))
})

const report = computed<PdfParseReport | undefined>(() => detail.value?.parseReport)

const errorMessage = computed(() => (
  reparseError.value ||
  detailError.value ||
  profilesError.value ||
  filesError.value
))

const selectedReparseTask = computed(() => (
  selectedFileId.value ? reparseTasksByFileId.value[selectedFileId.value] : undefined
))

const isSelectedFileReparsing = computed(() => (
  isReparsing.value && reparsingFileId.value === selectedFileId.value
))

const selectedParserProfile = computed(() => {
  return parserProfiles.value.find((profile) => profile.id === selectedParserProfileId.value)
})

onMounted(() => {
  void loadFiles()
  void loadParserProfiles()
})

watch(selectedFileId, (fileId) => {
  if (!fileId) {
    detailRequestId += 1
    detail.value = null
    detailError.value = ''
    return
  }
  void loadDetail(fileId)
})

async function loadFiles(preferredFileId = selectedFileId.value): Promise<void> {
  isLoadingFiles.value = true
  filesError.value = ''
  try {
    files.value = await listPdfKnowledgeFiles()
    selectedFileId.value =
      pdfFiles.value.find((file) => file.id === preferredFileId)?.id ??
      pdfFiles.value[0]?.id ??
      ''
    filePage.value = Math.min(filePage.value, filePageCount.value)
  } catch (error: unknown) {
    filesError.value = toErrorMessage(error)
  } finally {
    isLoadingFiles.value = false
  }
}

async function loadParserProfiles(): Promise<void> {
  isLoadingProfiles.value = true
  profilesError.value = ''
  try {
    const response = await listPdfParserProfiles()
    parserProfiles.value = response.profiles
    selectedParserProfileId.value = response.selectedProfileId
  } catch (error: unknown) {
    profilesError.value = toErrorMessage(error)
  } finally {
    isLoadingProfiles.value = false
  }
}

async function selectParserProfile(profileId: string): Promise<void> {
  if (
    !props.isAdmin ||
    isUpdatingProfile.value ||
    profileId === selectedParserProfileId.value
  ) {
    return
  }
  const profile = parserProfiles.value.find((item) => item.id === profileId)
  if (!profile?.available) {
    return
  }
  isUpdatingProfile.value = true
  profilesError.value = ''
  try {
    const response = await updatePdfParserProfile(profileId)
    parserProfiles.value = response.profiles
    selectedParserProfileId.value = response.selectedProfileId
  } catch (error: unknown) {
    profilesError.value = toErrorMessage(error)
  } finally {
    isUpdatingProfile.value = false
  }
}

async function loadDetail(fileId: string): Promise<void> {
  const requestId = ++detailRequestId
  isLoadingDetail.value = true
  detailError.value = ''
  try {
    const nextDetail = await getPdfDocumentDetail(fileId)
    if (requestId === detailRequestId) {
      detail.value = nextDetail
    }
  } catch (error: unknown) {
    if (requestId === detailRequestId) {
      detail.value = null
      detailError.value = toErrorMessage(error)
    }
  } finally {
    if (requestId === detailRequestId) {
      isLoadingDetail.value = false
    }
  }
}

async function reparseSelectedFile(): Promise<void> {
  if (!props.isAdmin || !selectedFileId.value || isReparsing.value) {
    return
  }
  isReparsing.value = true
  const fileId = selectedFileId.value
  reparsingFileId.value = fileId
  const nextTasks = { ...reparseTasksByFileId.value }
  delete nextTasks[fileId]
  reparseTasksByFileId.value = nextTasks
  reparseTaskPolling.stopPolling()
  reparseError.value = ''
  try {
    const task = await reparsePdfDocument(fileId)
    setReparseTask(fileId, task)
    if (isTerminalUploadTask(task)) {
      await finishReparse(fileId, task)
      return
    }
    reparseTaskPolling.startPolling({
      load: () => getPdfUploadTask(task.id),
      isTerminal: isTerminalUploadTask,
      onUpdate: (nextTask) => {
        setReparseTask(fileId, nextTask)
      },
      onTerminal: (nextTask) => finishReparse(fileId, nextTask),
      onError: (error, isFinalAttempt) => {
        if (isFinalAttempt) {
          isReparsing.value = false
          reparsingFileId.value = ''
          reparseError.value = toErrorMessage(error)
        }
      },
    })
  } catch (error: unknown) {
    isReparsing.value = false
    reparsingFileId.value = ''
    reparseError.value = toErrorMessage(error)
  }
}

async function finishReparse(fileId: string, task: PdfUploadTask): Promise<void> {
  setReparseTask(fileId, task)
  await loadFiles()
  if (selectedFileId.value === fileId) {
    await loadDetail(fileId)
  }
  isReparsing.value = false
  reparsingFileId.value = ''
  if (task.status !== 'ready') {
    reparseError.value = task.errorMessage || `Reparse ${task.status}.`
  }
}

function setReparseTask(fileId: string, task: PdfUploadTask): void {
  reparseTasksByFileId.value = {
    ...reparseTasksByFileId.value,
    [fileId]: task,
  }
}

function filePath(file: PdfManagedFile): string {
  const path = [file.name]
  const visited = new Set([file.id])
  let parent = file.parentId ? fileLookup.value.get(file.parentId) : undefined
  while (parent && !visited.has(parent.id)) {
    path.unshift(parent.name)
    visited.add(parent.id)
    parent = parent.parentId ? fileLookup.value.get(parent.parentId) : undefined
  }
  path.unshift('Knowledge Base')
  return path.join(' / ')
}

function isTerminalUploadTask(task: PdfUploadTask): boolean {
  return ['ready', 'failed', 'cancelled'].includes(task.status)
}

function qualityLabel(value?: string): string {
  if (value === 'good') {
    return 'Good'
  }
  if (value === 'warning') {
    return 'Warning'
  }
  if (value === 'partial') {
    return 'Partial'
  }
  if (value === 'failed') {
    return 'Failed'
  }
  return 'Unknown'
}

function percent(value?: number): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A'
  }
  return `${Math.round(value * 100)}%`
}

function parserProfileIcon(profile: PdfParserProfile): string {
  return profile.kind === 'cloud' ? 'settings' : 'description'
}

function parserProfileState(profile: PdfParserProfile): string {
  if (profile.isSelected) {
    return 'Selected'
  }
  if (!profile.available) {
    return 'Unavailable'
  }
  return 'Available'
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF diagnostics failed to load.'
}
</script>

<template>
  <main class="pdfdiag">
    <header class="pdfdiag-topbar">
      <div>
        <p>PDF Diagnostics</p>
        <h1>Parse Quality</h1>
      </div>
      <button type="button" @click="emit('openPdfWorkspace')">
        <AppIcon name="folder_open" />
        <span>PDF Workspace</span>
      </button>
    </header>

    <section class="pdfdiag-layout">
      <aside class="pdfdiag-files" aria-label="PDF files">
        <div class="pdfdiag-panel-head">
          <strong>Documents</strong>
          <span>{{ pdfFiles.length }} PDFs</span>
        </div>

        <div v-if="isLoadingFiles" class="pdfdiag-empty">
          <AppIcon name="refresh" />
          <strong>Loading files</strong>
        </div>
        <div v-else-if="pdfFiles.length === 0" class="pdfdiag-empty">
          <AppIcon name="description" />
          <strong>No PDF files</strong>
          <span>Upload PDFs from the PDF workspace.</span>
        </div>
        <button
          v-else
          v-for="file in paginatedPdfFiles"
          :key="file.id"
          type="button"
          class="pdfdiag-file"
          :class="{ active: file.id === selectedFileId }"
          @click="selectedFileId = file.id"
        >
          <AppIcon name="description" />
          <span>
            <strong>{{ file.name }}</strong>
            <small>
              {{ filePath(file) }} · {{ file.statusDetail || file.modifiedLabel }}
            </small>
          </span>
          <em :class="file.qualityStatus || file.status">
            {{ qualityLabel(file.qualityStatus || file.status) }}
          </em>
        </button>
        <div v-if="filePageCount > 1" class="pdfmgmt-pagination file-pagination">
          <button
            type="button"
            :disabled="filePage <= 1"
            @click="filePage -= 1"
          >
            <AppIcon name="chevron_left" />
            Prev
          </button>
          <span>{{ filePage }} / {{ filePageCount }}</span>
          <button
            type="button"
            :disabled="filePage >= filePageCount"
            @click="filePage += 1"
          >
            Next
            <AppIcon name="chevron_right" />
          </button>
        </div>
      </aside>

      <section class="pdfdiag-detail">
        <p v-if="errorMessage" class="pdfdiag-error">{{ errorMessage }}</p>

        <section class="pdfdiag-card pdfdiag-parser-card">
          <div class="pdfdiag-panel-head">
            <strong>Parsing Engine</strong>
            <span v-if="isLoadingProfiles">Loading</span>
            <span v-else>{{ selectedParserProfile?.label || 'Not selected' }}</span>
          </div>
          <div v-if="isLoadingProfiles" class="pdfdiag-empty compact">
            <AppIcon name="refresh" />
            <strong>Loading parser profiles</strong>
          </div>
          <div v-else class="pdfdiag-parser-grid">
            <button
              v-for="profile in parserProfiles"
              :key="profile.id"
              type="button"
              class="pdfdiag-parser-option"
              :class="{ active: profile.isSelected, unavailable: !profile.available }"
              :disabled="!isAdmin || isUpdatingProfile || !profile.available"
              @click="selectParserProfile(profile.id)"
            >
              <AppIcon :name="parserProfileIcon(profile)" />
              <span>
                <strong>{{ profile.label }}</strong>
                <small>{{ profile.description || profile.detail }}</small>
              </span>
              <em>{{ parserProfileState(profile) }}</em>
              <dl>
                <div>
                  <dt>Backend</dt>
                  <dd>{{ profile.backend }}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{{ profile.version || 'N/A' }}</dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>{{ profile.command || 'Configured service' }}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{{ profile.detail }}</dd>
                </div>
              </dl>
            </button>
          </div>
        </section>

        <div v-if="isLoadingDetail" class="pdfdiag-empty large">
          <AppIcon name="refresh" />
          <strong>Loading parse report</strong>
        </div>

        <div v-else-if="!selectedFile" class="pdfdiag-empty large">
          <AppIcon name="description" />
          <strong>Select a PDF</strong>
          <span>Parse diagnostics will appear here.</span>
        </div>

        <template v-else>
          <section class="pdfdiag-summary">
            <div>
              <span>Quality</span>
              <strong :class="report?.qualityStatus">
                {{ qualityLabel(report?.qualityStatus) }}
              </strong>
            </div>
            <div>
              <span>Coverage</span>
              <strong>{{ percent(report?.coverageRatio) }}</strong>
            </div>
            <div>
              <span>Pages</span>
              <strong>{{ report?.parsedPages ?? 0 }} / {{ report?.totalPages ?? selectedFile.pageCount ?? 0 }}</strong>
            </div>
            <div>
              <span>Warnings</span>
              <strong>{{ report?.warningCount ?? 0 }}</strong>
            </div>
          </section>

          <section class="pdfdiag-card">
            <div class="pdfdiag-panel-head">
              <strong>{{ selectedFile.name }}</strong>
              <button
                type="button"
                class="pdfdiag-inline-action"
                :disabled="!isAdmin || isReparsing"
                @click="reparseSelectedFile"
              >
                <AppIcon name="refresh" />
                <span>
                  {{
                    isSelectedFileReparsing
                      ? `Reparsing ${selectedReparseTask?.progress ?? 0}%`
                      : 'Reparse'
                  }}
                </span>
              </button>
            </div>
            <div v-if="!report" class="pdfdiag-empty">
              <AppIcon name="info" />
              <strong>No parse report yet</strong>
              <span>The document may still be queued or was parsed before diagnostics existed.</span>
            </div>
            <div v-else class="pdfdiag-metrics">
              <span>Chunks <strong>{{ report.chunkCount }}</strong></span>
              <span>Failed pages <strong>{{ report.failedPages }}</strong></span>
              <span>Empty pages <strong>{{ report.emptyPages }}</strong></span>
              <span>Text blocks <strong>{{ report.textBlockCount }}</strong></span>
              <span>Artifacts <strong>{{ report.artifacts.length }}</strong></span>
            </div>
          </section>

          <section v-if="report?.warnings.length" class="pdfdiag-card">
            <div class="pdfdiag-panel-head">
              <strong>Warnings</strong>
              <span>{{ report.warnings.length }}</span>
            </div>
            <ul class="pdfdiag-warning-list">
              <li v-for="warning in report.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </section>

          <section v-if="report" class="pdfdiag-card">
            <div class="pdfdiag-panel-head">
              <strong>Page Status</strong>
              <span>{{ report.pages.length }} pages</span>
            </div>
            <div class="pdfdiag-page-list">
              <div v-for="page in report.pages" :key="page.id" class="pdfdiag-page-row">
                <span>{{ page.pageLabel }}</span>
                <strong :class="page.status">{{ page.status.replace('_', ' ') }}</strong>
                <small>{{ page.charCount }} chars</small>
              </div>
            </div>
          </section>

          <section v-if="report?.artifacts.length" class="pdfdiag-card">
            <div class="pdfdiag-panel-head">
              <strong>Artifacts</strong>
              <span>{{ report.parserBackend || selectedFile.parserBackend || 'Unknown parser' }}</span>
            </div>
            <div class="pdfdiag-artifact-list">
              <div
                v-for="artifact in report.artifacts"
                :key="artifact.id"
                class="pdfdiag-artifact-row"
              >
                <span>
                  <strong>{{ artifact.name }}</strong>
                  <small>{{ artifact.path || 'No stored path' }}</small>
                </span>
                <em>{{ artifact.artifactType }}</em>
              </div>
            </div>
          </section>
        </template>
      </section>
    </section>
  </main>
</template>
