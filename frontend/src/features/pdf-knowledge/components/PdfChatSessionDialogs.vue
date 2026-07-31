<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfRecentChat } from '../types'

const props = defineProps<{
  activeSessionId: string
  pendingRenameChat: PdfRecentChat | null
  renameDraft: string
  renameError: string
  isRenamePending: boolean
  canSubmitRename: boolean
  pendingDeleteChats: PdfRecentChat[]
  deleteError: string
  isDeletePending: boolean
}>()

const emit = defineEmits<{
  updateRenameDraft: [value: string]
  closeRename: []
  submitRename: []
  closeDelete: []
  confirmDelete: []
}>()

function handleDocumentKeyDown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  if (props.pendingRenameChat) {
    event.preventDefault()
    event.stopImmediatePropagation()
    emit('closeRename')
  } else if (props.pendingDeleteChats.length > 0) {
    event.preventDefault()
    event.stopImmediatePropagation()
    emit('closeDelete')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleDocumentKeyDown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDocumentKeyDown, true)
})
</script>

<template>
  <section
    v-if="pendingRenameChat"
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="pdf-chat-rename-title"
    @click.self="emit('closeRename')"
  >
    <form class="app-dialog pdfkb-session-dialog" @submit.prevent="emit('submitRename')">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">PDF Chat Session</p>
          <h3 id="pdf-chat-rename-title">Rename chat</h3>
        </div>
        <button
          type="button"
          class="dialog-icon-button"
          aria-label="Close rename chat dialog"
          :disabled="isRenamePending"
          @click="emit('closeRename')"
        >
          <AppIcon name="close" />
        </button>
      </div>

      <label class="dialog-field">
        <span>Chat title</span>
        <input
          :value="renameDraft"
          type="text"
          maxlength="120"
          autocomplete="off"
          autofocus
          :disabled="isRenamePending"
          @input="emit(
            'updateRenameDraft',
            ($event.target as HTMLInputElement).value,
          )"
        />
      </label>

      <p v-if="renameError" class="dialog-error" role="alert">
        {{ renameError }}
      </p>

      <div class="dialog-actions">
        <button
          type="button"
          class="dialog-secondary"
          :disabled="isRenamePending"
          @click="emit('closeRename')"
        >
          Cancel
        </button>
        <button
          type="submit"
          class="dialog-primary"
          :disabled="!canSubmitRename || isRenamePending"
        >
          {{ isRenamePending ? 'Saving…' : 'Save' }}
        </button>
      </div>
    </form>
  </section>

  <section
    v-else-if="pendingDeleteChats.length > 0"
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="pdf-chat-delete-title"
    @click.self="emit('closeDelete')"
  >
    <div class="app-dialog pdfkb-session-dialog">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">PDF Chat Session</p>
          <h3 id="pdf-chat-delete-title">
            Delete {{ pendingDeleteChats.length === 1 ? 'chat' : 'chats' }}
          </h3>
        </div>
        <button
          type="button"
          class="dialog-icon-button"
          aria-label="Close delete chat dialog"
          :disabled="isDeletePending"
          @click="emit('closeDelete')"
        >
          <AppIcon name="close" />
        </button>
      </div>

      <p class="dialog-copy">
        <template v-if="pendingDeleteChats.length === 1">
          Delete “{{ pendingDeleteChats[0]?.title }}” and all of its saved turns?
        </template>
        <template v-else>
          Delete {{ pendingDeleteChats.length }} selected chats and all of their
          saved turns?
        </template>
        <template
          v-if="pendingDeleteChats.some((chat) => chat.id === activeSessionId)"
        >
          The active chat will be closed.
        </template>
      </p>

      <p v-if="deleteError" class="dialog-error" role="alert">
        {{ deleteError }}
      </p>

      <div class="dialog-actions">
        <button
          type="button"
          class="dialog-secondary"
          :disabled="isDeletePending"
          @click="emit('closeDelete')"
        >
          Cancel
        </button>
        <button
          type="button"
          class="dialog-danger"
          :disabled="isDeletePending"
          @click="emit('confirmDelete')"
        >
          {{ isDeletePending ? 'Deleting…' : 'Delete' }}
        </button>
      </div>
    </div>
  </section>
</template>
