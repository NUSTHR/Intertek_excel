<script setup lang="ts">
import { ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'

const props = defineProps<{
  accept: string
  disabled: boolean
  helpText: string
}>()

const emit = defineEmits<{
  select: [file: File | null]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

function openPicker(): void {
  if (props.disabled) {
    return
  }
  if (isDragging.value) {
    isDragging.value = false
  }
  fileInput.value?.click()
}

function handleFileChange(event: Event): void {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) {
    return
  }
  emit('select', input.files?.[0] ?? null)
  input.value = ''
}

function handleDragEnter(): void {
  if (props.disabled) {
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

function handleDrop(event: DragEvent): void {
  isDragging.value = false
  if (props.disabled) {
    return
  }
  emit('select', event.dataTransfer?.files?.[0] ?? null)
}
</script>

<template>
  <input
    ref="fileInput"
    class="visually-hidden"
    type="file"
    :accept="accept"
    @change="handleFileChange"
  />

  <button
    type="button"
    class="file-upload-zone"
    :class="{ dragging: isDragging }"
    :disabled="disabled"
    @click="openPicker"
    @dragenter.prevent="handleDragEnter"
    @dragover.prevent="handleDragEnter"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <span class="file-upload-icon">
      <AppIcon name="upload_file" />
    </span>
    <strong>Click or drag files to upload</strong>
    <span>{{ helpText }}</span>
  </button>
</template>
