<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfRecentChat } from '../types'

const props = defineProps<{
  chats: PdfRecentChat[]
  activeSessionId: string
  pendingSessionId: string
  isSessionLoading: boolean
  isStartingNewChat: boolean
  isSelectionMode: boolean
  isAllSelected: boolean
  isBatchPending: boolean
  selectedSessionIds: Set<string>
  busySessionIds: Set<string>
  errorMessage: string
}>()

const emit = defineEmits<{
  newChat: []
  openChat: [chatId: string]
  beginSelection: [sessionId?: string]
  cancelSelection: []
  toggleSelection: [sessionId: string]
  toggleSelectAll: []
  renameChat: [chat: PdfRecentChat]
  togglePinned: [chat: PdfRecentChat]
  deleteChat: [chat: PdfRecentChat]
  pinSelected: []
  unpinSelected: []
  deleteSelected: []
}>()

const openActionMenuId = ref('')
const chatList = ref<HTMLElement | null>(null)

function isBusy(chat: PdfRecentChat): boolean {
  return props.busySessionIds.has(chat.id)
}

function toggleActionMenu(sessionId: string): void {
  openActionMenuId.value =
    openActionMenuId.value === sessionId ? '' : sessionId
  if (!openActionMenuId.value) {
    return
  }
  void nextTick(() => {
    const menu = chatList.value?.querySelector<HTMLElement>(
      `[data-session-id="${CSS.escape(sessionId)}"] .pdfkb-session-action-menu`,
    )
    menu?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
}

function closeActionMenu(): void {
  openActionMenuId.value = ''
}

function emitMenuAction(action: () => void): void {
  closeActionMenu()
  action()
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!openActionMenuId.value) {
    return
  }
  const target = event.target
  if (
    target instanceof Element
    && target.closest('.pdfkb-session-action-menu, .pdfkb-session-menu-trigger')
  ) {
    return
  }
  closeActionMenu()
}

function handleDocumentKeyDown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') {
    return
  }
  if (openActionMenuId.value) {
    closeActionMenu()
    return
  }
  if (props.isSelectionMode) {
    emit('cancelSelection')
  }
}

watch(
  () => [props.chats, props.isSelectionMode] as const,
  ([chats, isSelectionMode]) => {
    if (
      openActionMenuId.value
      && !chats.some((chat) => chat.id === openActionMenuId.value)
    ) {
      closeActionMenu()
    }
    if (isSelectionMode) {
      closeActionMenu()
    }
  },
)

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeyDown)
})
</script>

<template>
  <section class="pdfkb-sidebar-panel pdfkb-chat-list-panel">
    <div class="pdfkb-section-title pdfkb-chat-section-title">
      <span>{{ isSelectionMode ? `${selectedSessionIds.size} Selected` : 'Recent Chats' }}</span>
      <span class="pdfkb-section-actions">
        <button
          v-if="!isSelectionMode"
          type="button"
          aria-label="New PDF chat"
          :disabled="isStartingNewChat"
          @click="emit('newChat')"
        >
          <AppIcon name="add" />
        </button>
        <button
          v-if="!isSelectionMode"
          type="button"
          aria-label="Select PDF chats"
          :disabled="chats.length === 0"
          @click="emit('beginSelection')"
        >
          <AppIcon name="checklist" />
        </button>
        <button
          v-else
          type="button"
          aria-label="Exit chat selection"
          :disabled="isBatchPending"
          @click="emit('cancelSelection')"
        >
          <AppIcon name="close" />
        </button>
      </span>
    </div>

    <div v-if="isSelectionMode" class="pdfkb-session-batch-toolbar">
      <button
        type="button"
        :aria-pressed="isAllSelected"
        :disabled="isBatchPending"
        @click="emit('toggleSelectAll')"
      >
        <AppIcon :name="isAllSelected ? 'check_box' : 'check_box_outline_blank'" />
        <span>{{ isAllSelected ? 'Clear all' : 'Select all' }}</span>
      </button>
      <span class="pdfkb-session-batch-actions">
        <button
          type="button"
          aria-label="Pin selected chats"
          :disabled="selectedSessionIds.size === 0 || isBatchPending"
          @click="emit('pinSelected')"
        >
          <AppIcon name="push_pin" />
        </button>
        <button
          type="button"
          aria-label="Unpin selected chats"
          :disabled="selectedSessionIds.size === 0 || isBatchPending"
          @click="emit('unpinSelected')"
        >
          <AppIcon name="keep_off" />
        </button>
        <button
          type="button"
          class="danger"
          aria-label="Delete selected chats"
          :disabled="selectedSessionIds.size === 0 || isBatchPending"
          @click="emit('deleteSelected')"
        >
          <AppIcon name="delete" />
        </button>
      </span>
    </div>

    <div
      ref="chatList"
      class="pdfkb-recent-chat-list"
      :class="{ 'has-open-menu': Boolean(openActionMenuId) }"
    >
      <div v-if="chats.length === 0" class="pdfkb-sidebar-empty">
        <AppIcon name="chat_bubble" />
        <strong>No recent chats</strong>
        <span>Start a PDF chat to keep history here.</span>
      </div>

      <article
        v-for="chat in chats"
        v-else
        :key="chat.id"
        :data-session-id="chat.id"
        class="pdfkb-recent-chat chat-session-item"
        :class="{
          active: chat.id === activeSessionId,
          pending: chat.id === pendingSessionId,
          pinned: Boolean(chat.pinnedAt),
          selected: selectedSessionIds.has(chat.id),
          'menu-open': openActionMenuId === chat.id,
        }"
        :aria-current="chat.id === activeSessionId ? 'true' : undefined"
      >
        <button
          v-if="!isSelectionMode"
          type="button"
          class="pdfkb-session-open"
          :aria-label="`Open chat ${chat.title}`"
          :aria-busy="chat.id === pendingSessionId"
          :disabled="isBusy(chat)"
          @click="emit('openChat', chat.id)"
          @keydown.enter.space.prevent="emit('openChat', chat.id)"
        >
          <span class="session-glyph">
            <AppIcon :name="chat.pinnedAt ? 'push_pin' : 'chat_bubble'" />
          </span>
          <span class="session-copy">
            <strong :title="chat.title">{{ chat.title }}</strong>
          </span>
        </button>
        <button
          v-else
          type="button"
          class="pdfkb-session-selection"
          :aria-label="`${selectedSessionIds.has(chat.id) ? 'Deselect' : 'Select'} chat ${chat.title}`"
          :aria-pressed="selectedSessionIds.has(chat.id)"
          :disabled="isBatchPending || isBusy(chat)"
          @click="emit('toggleSelection', chat.id)"
          @keydown.enter.space.prevent="emit('toggleSelection', chat.id)"
        >
          <AppIcon
            :name="selectedSessionIds.has(chat.id)
              ? 'check_box'
              : 'check_box_outline_blank'"
          />
          <span class="session-glyph">
            <AppIcon :name="chat.pinnedAt ? 'push_pin' : 'chat_bubble'" />
          </span>
          <span class="session-copy">
            <strong :title="chat.title">{{ chat.title }}</strong>
          </span>
        </button>

        <span
          v-if="!isSelectionMode"
          class="session-actions"
          @click.stop
        >
          <button
            type="button"
            class="menu-trigger compact pdfkb-session-menu-trigger"
            :class="{ active: openActionMenuId === chat.id }"
            :aria-label="`Actions for chat ${chat.title}`"
            :aria-expanded="openActionMenuId === chat.id"
            :disabled="isBusy(chat)"
            @click="toggleActionMenu(chat.id)"
          >
            <AppIcon name="more_vert" />
          </button>
        </span>

        <span
          v-if="openActionMenuId === chat.id"
          class="item-action-menu session-action-menu pdfkb-session-action-menu"
          @click.stop
        >
          <button
            type="button"
            @click="emitMenuAction(() => emit('togglePinned', chat))"
          >
            <AppIcon :name="chat.pinnedAt ? 'keep_off' : 'push_pin'" />
            {{ chat.pinnedAt ? 'Unpin' : 'Pin' }}
          </button>
          <button
            type="button"
            @click="emitMenuAction(() => emit('renameChat', chat))"
          >
            <AppIcon name="edit" />
            Rename
          </button>
          <button
            type="button"
            @click="emitMenuAction(() => emit('beginSelection', chat.id))"
          >
            <AppIcon name="checklist" />
            Select
          </button>
          <button
            type="button"
            class="danger-text"
            @click="emitMenuAction(() => emit('deleteChat', chat))"
          >
            <AppIcon name="delete" />
            Delete
          </button>
        </span>
      </article>
    </div>

    <p v-if="errorMessage" class="pdfkb-session-action-error" role="alert">
      {{ errorMessage }}
    </p>
  </section>
</template>
