<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import { fileWorkspaceCopy } from '../copy'

withDefaults(defineProps<{
  open: boolean
  mode: 'rename' | 'delete'
  kindLabel: string
  displayName: string
  draft?: string
  description?: string
  errorMessage?: string
  isBusy?: boolean
}>(), {
  draft: '',
  description: '',
  errorMessage: '',
  isBusy: false,
})

const emit = defineEmits<{
  cancel: []
  confirm: []
  updateDraft: [value: string]
}>()

function inputValue(event: Event): string {
  return event.target instanceof HTMLInputElement ? event.target.value : ''
}
</script>

<template>
  <section
    v-if="open"
    class="dialog-backdrop"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="`file-workspace-${mode}-dialog-title`"
    @click.self="emit('cancel')"
    @keydown.esc="emit('cancel')"
  >
    <form class="app-dialog" @submit.prevent="emit('confirm')">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">{{ kindLabel }}</p>
          <h3 :id="`file-workspace-${mode}-dialog-title`">
            {{ mode === 'rename' ? fileWorkspaceCopy.actions.rename : fileWorkspaceCopy.actions.delete }}
          </h3>
        </div>
        <button
          type="button"
          class="dialog-icon-button"
          aria-label="Close"
          :disabled="isBusy"
          @click="emit('cancel')"
        ><AppIcon name="close" /></button>
      </div>

      <template v-if="mode === 'rename'">
        <p class="dialog-copy">Rename "{{ displayName }}" without changing its contents.</p>
        <label class="dialog-field">
          <span>Name</span>
          <input
            :value="draft"
            type="text"
            autocomplete="off"
            autofocus
            :disabled="isBusy"
            @input="emit('updateDraft', inputValue($event))"
          />
        </label>
      </template>
      <p v-else class="dialog-copy">{{ description }}</p>

      <p v-if="errorMessage" class="dialog-error" role="alert">{{ errorMessage }}</p>
      <div class="dialog-actions">
        <button type="button" class="dialog-secondary" :disabled="isBusy" @click="emit('cancel')">
          Cancel
        </button>
        <button
          type="submit"
          :class="mode === 'delete' ? 'dialog-danger' : 'dialog-primary'"
          :disabled="isBusy || (mode === 'rename' && !draft.trim())"
        >
          {{ isBusy ? (mode === 'delete' ? 'Deleting…' : 'Saving…') : (mode === 'delete' ? fileWorkspaceCopy.actions.delete : 'Save') }}
        </button>
      </div>
    </form>
  </section>
</template>
