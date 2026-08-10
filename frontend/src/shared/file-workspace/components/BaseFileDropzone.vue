<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { matchesAccept, parseAccept, type AcceptClause } from '../file-accept'
import type {
  BaseDropzoneEmits,
  BaseDropzoneProps,
  DropzoneValidationError,
  DropzoneValidationErrorCode,
} from '../file-dropzone-contract'

const props = withDefaults(defineProps<BaseDropzoneProps>(), {
  multiple: false,
  isDisabled: false,
  promptLabel: 'Upload',
})

const emit = defineEmits<BaseDropzoneEmits>()

const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

const acceptList = computed<AcceptClause[]>(() => parseAccept(props.accept))

const fileTypeMatcher = computed<(file: File) => boolean>(() => {
  const accepted = acceptList.value
  if (accepted.length === 0) {
    return () => true
  }
  return (file) => matchesAccept(file, accepted)
})

function openPicker(): void {
  if (props.isDisabled) {
    return
  }
  if (isDragging.value) {
    isDragging.value = false
  }
  emit('pickerOpened')
  fileInput.value?.click()
}

function emitFiles(files: File[]): void {
  if (files.length === 0) {
    return
  }
  if (!props.multiple && files.length > 1) {
    emit('validationError', 'Only one file can be uploaded at a time.')
    return
  }
  const validated: File[] = []
  let firstError: DropzoneValidationError | null = null
  for (const file of files) {
    const error = validateFile(file)
    if (error) {
      if (!firstError) {
        firstError = error
      }
      continue
    }
    validated.push(file)
    if (!props.multiple) {
      break
    }
  }
  if (firstError) {
    emit('validationError', firstError.message)
    return
  }
  emit('filesSelected', validated)
}

function handleFileChange(event: Event): void {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  emitFiles(Array.from(input.files ?? []))
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

function handleDrop(event: DragEvent): void {
  isDragging.value = false
  if (props.isDisabled) {
    return
  }
  event.preventDefault()
  const transfer = event.dataTransfer
  if (!transfer) {
    return
  }
  // Prefer `items` so we can reliably resolve Folders vs Files in modern
  // browsers; fall back to `files` otherwise.
  const files = resolveDataTransferFiles(transfer)
  emitFiles(files)
}

function resolveDataTransferFiles(transfer: DataTransfer): File[] {
  if (transfer.items && transfer.items.length > 0) {
    const files: File[] = []
    for (let index = 0; index < transfer.items.length; index += 1) {
      const item = transfer.items[index]
      if (item.kind !== 'file') {
        continue
      }
      const file = item.getAsFile()
      if (file) {
        files.push(file)
      }
    }
    if (files.length > 0) {
      return files
    }
  }
  return Array.from(transfer.files ?? [])
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

  <button
    type="button"
    class="file-workspace-base-dropzone"
    :data-dragging="isDragging"
    :disabled="isDisabled"
    @click="openPicker"
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
  </button>
</template>
