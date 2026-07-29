<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import WorkbookUploadDropzone from './WorkbookUploadDropzone.vue'
import { fileIcon, fileTypeLabel, formatDate } from '../../../app/workspace-utils'

import type { ExcelFile } from '../../../types/excel-assets'

const props = defineProps<{
  files: ExcelFile[]
  totalFileCount: number
  selectedFileId: string
  openMenuFileId: string
  pinnedFileIds: string[]
  disabled: boolean
  searchTerm: string
  uploadAccept: string
  uploadHelpText: string
  currentPage: number
  pageCount: number
  visiblePages: number[]
  paginationLabel: string
}>()

const emit = defineEmits<{
  uploadSelected: [file: File | null]
  selectFile: [file: ExcelFile]
  toggleMenu: [fileId: string]
  togglePin: [file: ExcelFile]
  renameFile: [file: ExcelFile]
  toggleVisibility: [file: ExcelFile]
  deleteFile: [file: ExcelFile]
  setPage: [page: number]
  stepPage: [direction: 1 | -1]
}>()

function isFilePinned(fileId: string): boolean {
  return props.pinnedFileIds.includes(fileId)
}

const hasSearchQuery = computed(() => props.searchTerm.trim().length > 0)

const emptyTitle = computed(() => (
  hasSearchQuery.value ? 'No matching workbooks' : 'Upload a workbook to get started'
))

const emptyDetail = computed(() => {
  return hasSearchQuery.value
    ? 'Try another filename or clear the search.'
    : 'Excel files will appear here after parsing is complete.'
})

function selectFile(file: ExcelFile): void {
  if (props.disabled) {
    return
  }
  emit('selectFile', file)
}
</script>

<template>
  <section class="file-list-panel">
    <div class="panel-heading">
      <div>
        <h3>File Sources</h3>
      </div>
      <span class="files-found-label">{{ totalFileCount }} Files Found</span>
    </div>

    <WorkbookUploadDropzone
      :accept="uploadAccept"
      :disabled="disabled"
      :help-text="uploadHelpText"
      @select="emit('uploadSelected', $event)"
    />

    <div class="file-card-list">
      <article
        v-for="file in files"
        :key="file.file_id"
        class="file-library-card"
        :class="{
          selected: file.file_id === selectedFileId,
          pinned: isFilePinned(file.file_id),
          'menu-open': openMenuFileId === file.file_id,
        }"
        :aria-disabled="disabled ? 'true' : undefined"
      >
        <button
          type="button"
          class="semantic-card-hitbox"
          :disabled="disabled"
          :aria-label="`Select ${file.display_name}`"
          @click="selectFile(file)"
        ></button>
        <span class="file-badge large"><AppIcon :name="fileIcon(file)" /></span>
        <span class="file-card-main">
          <strong>{{ file.display_name }}</strong>
          <span class="file-meta-line">
            {{ fileTypeLabel(file) }} - Modified {{ formatDate(file.updated_at) }}
          </span>
          <span
            v-if="!file.visible_to_members"
            class="file-visibility-chip"
            title="Hidden from workspace users"
          >
            <AppIcon name="visibility_off" />
            Admin only
          </span>
        </span>
        <span class="file-card-actions" @click.stop>
          <button
            type="button"
            class="menu-trigger"
            :disabled="disabled"
            :aria-expanded="openMenuFileId === file.file_id"
            aria-label="File actions"
            @click="emit('toggleMenu', file.file_id)"
          >
            <AppIcon name="more_vert" />
          </button>
        </span>
        <span
          v-if="openMenuFileId === file.file_id"
          class="item-action-menu file-card-menu"
          @click.stop
        >
          <button type="button" @click="emit('togglePin', file)">
            <AppIcon name="push_pin" />
            {{ isFilePinned(file.file_id) ? 'Unpin' : 'Pin' }}
          </button>
          <button type="button" :disabled="disabled" @click="emit('renameFile', file)">
            <AppIcon name="edit" />
            Rename
          </button>
          <button type="button" :disabled="disabled" @click="emit('toggleVisibility', file)">
            <AppIcon :name="file.visible_to_members ? 'visibility_off' : 'visibility'" />
            {{ file.visible_to_members ? 'Hide from members' : 'Show to members' }}
          </button>
          <button
            type="button"
            class="danger-text"
            :disabled="disabled"
            @click="emit('deleteFile', file)"
          >
            <AppIcon name="close" />
            Delete
          </button>
        </span>
      </article>

      <div v-if="totalFileCount === 0" class="file-empty-panel">
        <span class="empty-state-mark" aria-hidden="true">
          <AppIcon :name="hasSearchQuery ? 'search' : 'folder_open'" />
        </span>
        <strong>{{ emptyTitle }}</strong>
        <span>{{ emptyDetail }}</span>
      </div>
    </div>

    <div class="file-pagination">
      <button
        type="button"
        class="pagination-link"
        :disabled="currentPage <= 1"
        @click="emit('stepPage', -1)"
      >
        <AppIcon name="chevron_left" />
        Previous
      </button>
      <div class="pagination-pages">
        <button
          v-for="pageNumber in visiblePages"
          :key="pageNumber"
          type="button"
          :class="{ active: pageNumber === currentPage }"
          :aria-current="pageNumber === currentPage ? 'page' : undefined"
          @click="emit('setPage', pageNumber)"
        >
          {{ pageNumber }}
        </button>
      </div>
      <span class="pagination-range">{{ paginationLabel }}</span>
      <button
        type="button"
        class="pagination-link"
        :disabled="currentPage >= pageCount"
        @click="emit('stepPage', 1)"
      >
        Next
        <AppIcon name="chevron_right" />
      </button>
    </div>
  </section>
</template>
