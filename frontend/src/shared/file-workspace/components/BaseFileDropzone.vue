<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { matchesAccept, parseAccept, type AcceptClause } from '../file-accept'
import { toFileUploadSelection } from '../file-upload-selection'
import type {
  BaseDropzoneEmits,
  BaseDropzoneProps,
  DropzoneValidationError,
  DropzoneValidationErrorCode,
} from '../file-dropzone-contract'
import type { FileUploadSelection } from '../../../types/file-upload'

interface DroppedFileSystemEntry {
  isFile: boolean
  isDirectory: boolean
  name: string
  file?: (
    successCallback: (file: File) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void
  createReader?: () => DroppedDirectoryReader
}

interface DroppedDirectoryReader {
  readEntries: (
    successCallback: (entries: DroppedFileSystemEntry[]) => void,
    errorCallback?: (error: DOMException) => void,
  ) => void
}

type DataTransferItemWithEntry = DataTransferItem & {
  webkitGetAsEntry?: () => DroppedFileSystemEntry | null
}

const props = withDefaults(defineProps<BaseDropzoneProps>(), {
  multiple: false,
  isDisabled: false,
  promptLabel: 'Upload',
  fileActionLabel: '',
  allowDirectories: false,
  directoryLabel: 'Choose folder',
})

const emit = defineEmits<BaseDropzoneEmits>()

const fileInput = ref<HTMLInputElement | null>(null)
const directoryInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

const acceptList = computed<AcceptClause[]>(() => parseAccept(props.accept))
const resolvedFileActionLabel = computed(() => (
  props.fileActionLabel.trim() || (props.multiple ? 'Choose files' : 'Choose file')
))

const fileTypeMatcher = computed<(file: File) => boolean>(() => {
  const accepted = acceptList.value
  if (accepted.length === 0) {
    return () => true
  }
  return (file) => matchesAccept(file, accepted)
})

function openFilePicker(): void {
  if (props.isDisabled) {
    return
  }
  if (isDragging.value) {
    isDragging.value = false
  }
  emit('pickerOpened')
  fileInput.value?.click()
}

function openDirectoryPicker(): void {
  if (props.isDisabled || !props.allowDirectories) {
    return
  }
  if (isDragging.value) {
    isDragging.value = false
  }
  emit('pickerOpened')
  directoryInput.value?.click()
}

function emitSelections(selections: FileUploadSelection[]): void {
  if (selections.length === 0) {
    return
  }
  if (!props.multiple && selections.length > 1) {
    emit('validationError', 'Only one file can be uploaded at a time.')
    return
  }
  const validated: FileUploadSelection[] = []
  const errors: DropzoneValidationError[] = []
  for (const selection of selections) {
    const error = validateFile(selection.file)
    if (error) {
      errors.push(error)
      continue
    }
    validated.push(selection)
    if (!props.multiple) {
      break
    }
  }
  if (validated.length === 0) {
    emit('validationError', errors[0]?.message || 'No supported files were found.')
    return
  }
  emit('filesSelected', validated)
  if (errors.length > 0) {
    const noun = errors.length === 1 ? 'file was' : 'files were'
    emit(
      'validationError',
      `${errors.length} ${noun} skipped. ${errors[0]?.message ?? ''}`.trim(),
    )
  }
}

function handleFileChange(event: Event): void {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  emitSelections(Array.from(input.files ?? []).map((file) => toFileUploadSelection(file)))
  input.value = ''
}

function handleDirectoryChange(event: Event): void {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  emitSelections(Array.from(input.files ?? []).map((file) => toFileUploadSelection(file)))
  input.value = ''
}

function handleDragEnter(): void {
  if (props.isDisabled) {
    return
  }
  isDragging.value = true
}

function handleDragLeave(event: DragEvent): void {
  if (!(event.currentTarget instanceof HTMLElement)) {
    isDragging.value = false
    return
  }
  const relatedTarget = event.relatedTarget
  if (!(relatedTarget instanceof Node) || !event.currentTarget.contains(relatedTarget)) {
    isDragging.value = false
  }
}

function handleDragOver(event: DragEvent): void {
  if (props.isDisabled) {
    return
  }
  // Required so `drop` fires in some browsers. The shared stylesheet
  // already provides a `data-dragging` indicator.
  event.preventDefault()
}

async function handleDrop(event: DragEvent): Promise<void> {
  isDragging.value = false
  if (props.isDisabled) {
    return
  }
  event.preventDefault()
  const transfer = event.dataTransfer
  if (!transfer) {
    return
  }
  try {
    const selections = await resolveDataTransferSelections(transfer)
    if (selections.length === 0) {
      emit(
        'validationError',
        props.allowDirectories
          ? 'No supported files were found in the dropped items.'
          : 'Folders cannot be uploaded here.',
      )
      return
    }
    emitSelections(selections)
  } catch (error: unknown) {
    emit(
      'validationError',
      error instanceof Error ? error.message : 'The dropped folder could not be read.',
    )
  }
}

async function resolveDataTransferSelections(
  transfer: DataTransfer,
): Promise<FileUploadSelection[]> {
  if (transfer.items && transfer.items.length > 0) {
    const selections: FileUploadSelection[] = []
    for (let index = 0; index < transfer.items.length; index += 1) {
      const item = transfer.items[index]
      if (item.kind !== 'file') {
        continue
      }
      const entry = (item as DataTransferItemWithEntry).webkitGetAsEntry?.() ?? null
      if (entry) {
        if (entry.isDirectory && !props.allowDirectories) {
          continue
        }
        selections.push(...await collectDroppedEntry(entry, ''))
        continue
      }
      const file = item.getAsFile()
      if (file) {
        selections.push(toFileUploadSelection(file))
      }
    }
    if (selections.length > 0) {
      return selections.sort((left, right) => left.relativePath.localeCompare(right.relativePath))
    }
  }
  return Array.from(transfer.files ?? []).map((file) => toFileUploadSelection(file))
}

async function collectDroppedEntry(
  entry: DroppedFileSystemEntry,
  parentPath: string,
): Promise<FileUploadSelection[]> {
  const relativePath = [parentPath, entry.name].filter(Boolean).join('/')
  if (entry.isFile && entry.file) {
    const file = await readDroppedFile(entry)
    return [toFileUploadSelection(file, relativePath)]
  }
  if (!entry.isDirectory || !entry.createReader) {
    return []
  }

  const children = await readAllDirectoryEntries(entry.createReader())
  const nested = await Promise.all(
    children.map((child) => collectDroppedEntry(child, relativePath)),
  )
  return nested.flat()
}

function readDroppedFile(entry: DroppedFileSystemEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file?.(
      resolve,
      () => reject(new Error(`Could not read ${entry.name}.`)),
    )
  })
}

async function readAllDirectoryEntries(
  reader: DroppedDirectoryReader,
): Promise<DroppedFileSystemEntry[]> {
  const entries: DroppedFileSystemEntry[] = []
  while (true) {
    const batch = await new Promise<DroppedFileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(
        resolve,
        () => reject(new Error('The dropped folder could not be read.')),
      )
    })
    if (batch.length === 0) {
      return entries
    }
    entries.push(...batch)
  }
}

function validateFile(file: File): DropzoneValidationError | null {
  if (file.size === 0) {
    return errorFor('empty-file', `${file.name} is empty.`, file.name)
  }
  if (props.maxSizeBytes > 0 && file.size > props.maxSizeBytes) {
    return errorFor(
      'file-too-large',
      `${file.name} exceeds the maximum allowed size.`,
      file.name,
    )
  }
  if (!fileTypeMatcher.value(file)) {
    return errorFor(
      'extension-mismatch',
      `${file.name} is not an accepted file type.`,
      file.name,
    )
  }
  return null
}

function errorFor(
  code: DropzoneValidationErrorCode,
  message: string,
  fileName?: string,
): DropzoneValidationError {
  return fileName ? { code, message, fileName } : { code, message }
}
</script>

<template>
  <input
    ref="fileInput"
    hidden
    type="file"
    aria-hidden="true"
    tabindex="-1"
    :accept="accept"
    :multiple="multiple"
    @change="handleFileChange"
  />
  <input
    v-if="allowDirectories"
    ref="directoryInput"
    hidden
    type="file"
    aria-hidden="true"
    tabindex="-1"
    :accept="accept"
    multiple
    webkitdirectory
    @change="handleDirectoryChange"
  />

  <div
    class="file-workspace-base-dropzone"
    :data-dragging="isDragging"
    :data-disabled="isDisabled"
    :data-directory-enabled="allowDirectories"
    @dragenter.prevent="handleDragEnter"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <span class="file-workspace-base-dropzone-icon" aria-hidden="true">
      <AppIcon name="upload_file" />
    </span>
    <span class="file-workspace-base-dropzone-copy">
      <strong>{{ promptLabel }}</strong>
      <small class="file-workspace-base-dropzone-help">{{ helpText }}</small>
    </span>
    <span class="file-workspace-base-dropzone-actions">
    <button
      type="button"
      class="file-workspace-base-dropzone-main"
      :disabled="isDisabled"
      @click="openFilePicker"
    >
      <AppIcon name="upload_file" />
      {{ resolvedFileActionLabel }}
    </button>
    <button
      v-if="allowDirectories"
      type="button"
      class="file-workspace-base-dropzone-directory"
      :disabled="isDisabled"
      @click="openDirectoryPicker"
    >
      <AppIcon name="folder_open" />
      {{ directoryLabel }}
    </button>
    </span>
  </div>
</template>
