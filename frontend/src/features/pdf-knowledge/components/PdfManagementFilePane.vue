<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type {
  PdfManagedFile,
  PdfManagedFileKind,
  PdfManagedFileStatus,
  PdfUploadTask,
} from '../types'

defineProps<{
  files: PdfManagedFile[]
  selectedFileId: string
  totalFileCount: number
  currentPage: number
  pageCount: number
  visiblePages: number[]
  uploadTasks: PdfUploadTask[]
  uploadTaskSummary: string
  isUploading: boolean
  isLoading: boolean
  errorMessage: string
}>()

const emit = defineEmits<{
  selectFile: [file: PdfManagedFile]
  requestUpload: []
  pageChange: [page: number]
  pageStep: [direction: -1 | 1]
}>()

function iconForFileKind(kind: PdfManagedFileKind): string {
  if (kind === 'folder') {
    return 'folder_open'
  }
  if (kind === 'csv') {
    return 'table_chart'
  }
  if (kind === 'xlsx') {
    return 'table_rows'
  }
  return 'description'
}

function statusLabel(status: PdfManagedFileStatus): string {
  if (status === 'indexed') {
    return 'Indexed'
  }
  if (status === 'parsing') {
    return 'Parsing'
  }
  if (status === 'uploading') {
    return 'Uploading'
  }
  if (status === 'indexing') {
    return 'Indexing'
  }
  if (status === 'queued') {
    return 'Queued'
  }
  if (status === 'failed') {
    return 'Failed'
  }
  return 'Ready'
}

function progressForFile(file: PdfManagedFile): number {
  return file.progress ?? (file.status === 'parsing' || file.status === 'indexing' ? 48 : 100)
}

</script>

<template>
  <section class="pdfmgmt-file-pane">
    <div class="pdfmgmt-file-scroll">
      <div class="pdfmgmt-breadcrumb-row">
        <nav aria-label="Knowledge path">
          <strong>Knowledge Base</strong>
        </nav>
        <span class="pdfmgmt-count-pill">{{ totalFileCount }} Files</span>
      </div>

      <button
        type="button"
        class="pdfmgmt-dropzone"
        :disabled="isUploading"
        @click="emit('requestUpload')"
      >
        <span class="pdfmgmt-dropzone-icon">
          <AppIcon name="upload_file" />
        </span>
        <span>
          <strong>{{ isUploading ? 'Preparing upload tasks...' : 'Click or drag files to upload' }}</strong>
          <small>PDF folders (Max 50MB per file)</small>
        </span>
      </button>

      <div v-if="uploadTaskSummary || uploadTasks.length" class="pdfmgmt-task-strip">
        <div>
          <AppIcon name="refresh" />
          <strong>{{ uploadTaskSummary || 'All tasks complete' }}</strong>
        </div>
        <span v-for="task in uploadTasks.slice(0, 2)" :key="task.id">
          {{ task.fileName }} - {{ task.stage }} / {{ task.parserBackend }} / {{ task.progress }}%
          <small v-if="task.errorCode">({{ task.errorCode }})</small>
        </span>
      </div>

      <p v-if="errorMessage" class="pdfmgmt-inline-error">{{ errorMessage }}</p>

      <div class="pdfmgmt-file-table" role="table" aria-label="Knowledge files">
        <div v-if="files.length > 0" class="pdfmgmt-file-header" role="row">
          <span>Type</span>
          <span>Name</span>
          <span>Size</span>
          <span>Status</span>
          <span></span>
        </div>

        <div v-if="isLoading" class="pdfmgmt-file-empty">
          <AppIcon name="refresh" />
          <strong>Loading knowledge files</strong>
        </div>

        <div v-else-if="files.length === 0" class="pdfmgmt-file-empty">
          <AppIcon name="folder_open" />
          <strong>No files match this view</strong>
          <span>Upload a folder or adjust the search term.</span>
        </div>

        <button
          v-else
          v-for="file in files"
          :key="file.id"
          type="button"
          class="pdfmgmt-file-row"
          :class="{
            active: file.id === selectedFileId,
            parsing: file.status === 'parsing' || file.status === 'indexing',
          }"
          role="row"
          @click="emit('selectFile', file)"
        >
          <span class="pdfmgmt-file-icon" :class="file.kind">
            <AppIcon :name="iconForFileKind(file.kind)" />
          </span>
          <span class="pdfmgmt-file-name">
            <strong>{{ file.name }}</strong>
            <small>{{ file.modifiedLabel }}</small>
          </span>
          <span class="pdfmgmt-file-size">{{ file.sizeLabel }}</span>
          <span class="pdfmgmt-status-wrap">
            <span class="pdfmgmt-status" :class="file.status">
              {{ statusLabel(file.status) }}
            </span>
            <span
              v-if="['uploading', 'queued', 'parsing', 'indexing'].includes(file.status)"
              class="pdfmgmt-progress-track"
            >
              <span
                class="pdfmgmt-progress-fill"
                :style="{ width: `${progressForFile(file)}%` }"
              ></span>
            </span>
          </span>
          <span class="pdfmgmt-row-menu">
            <AppIcon name="more_vert" />
          </span>
        </button>
      </div>

      <div class="pdfmgmt-pagination">
        <button type="button" :disabled="currentPage <= 1" @click="emit('pageStep', -1)">
          <AppIcon name="chevron_left" />
          Prev
        </button>
        <div>
          <button
            v-for="page in visiblePages"
            :key="page"
            type="button"
            :class="{ active: page === currentPage }"
            @click="emit('pageChange', page)"
          >
            {{ page }}
          </button>
        </div>
        <button type="button" :disabled="currentPage >= pageCount" @click="emit('pageStep', 1)">
          Next
          <AppIcon name="chevron_right" />
        </button>
      </div>
    </div>
  </section>
</template>
