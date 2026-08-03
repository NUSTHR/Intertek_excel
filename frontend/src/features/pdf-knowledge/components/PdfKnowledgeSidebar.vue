<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { PdfKnowledgeNode, PdfRecentChat, PdfSidebarView } from '../types'
import PdfKnowledgeTreeNode from './PdfKnowledgeTreeNode.vue'
import PdfRecentChatList from './PdfRecentChatList.vue'

defineProps<{
  activeView: PdfSidebarView
  errorMessage: string
  selectedContextId: string
  isSessionLoading: boolean
  pendingSessionId: string
  isStartingNewChat: boolean
  activeSessionId: string
  tree: PdfKnowledgeNode[]
  recentChats: PdfRecentChat[]
  isChatSelectionMode: boolean
  isAllChatsSelected: boolean
  isChatBatchPending: boolean
  selectedSessionIds: Set<string>
  busySessionIds: Set<string>
  sessionActionError: string
}>()

const emit = defineEmits<{
  changeView: [view: PdfSidebarView]
  newChat: []
  openChat: [chatId: string]
  beginChatSelection: [sessionId?: string]
  cancelChatSelection: []
  toggleChatSelection: [sessionId: string]
  toggleSelectAllChats: []
  renameChat: [chat: PdfRecentChat]
  toggleChatPinned: [chat: PdfRecentChat]
  deleteChat: [chat: PdfRecentChat]
  pinSelectedChats: []
  unpinSelectedChats: []
  deleteSelectedChats: []
  selectContext: [fileId: string]
}>()

</script>

<template>
  <nav
    class="pdfkb-sidebar chat-session-rail excelai-side-nav"
    aria-label="PDF knowledge navigation"
  >
    <div class="pdfkb-brand-block chat-rail-brand">
      <div class="pdfkb-brand-mark rail-logo">
        <AppIcon name="description" />
      </div>
      <div>
        <h3>PDF AI</h3>
        <p>Researcher Pro</p>
      </div>
    </div>

    <div class="pdfkb-sidebar-cta">
      <button
        type="button"
        class="pdfkb-new-chat new-chat-button"
        :disabled="isStartingNewChat"
        @click="emit('newChat')"
      >
        <AppIcon name="add" />
        <strong>New Chat</strong>
      </button>
    </div>

    <div class="pdfkb-sidebar-scroll">
      <div class="pdfkb-switcher" role="tablist" aria-label="Sidebar mode">
        <span
          class="pdfkb-switcher-pill"
          :class="{ 'move-right': activeView === 'chats' }"
          aria-hidden="true"
        ></span>
        <button
          type="button"
          role="tab"
          class="pdfkb-switcher-tab"
          :class="{ active: activeView === 'knowledge' }"
          :aria-selected="activeView === 'knowledge'"
          aria-label="Knowledge Base"
          @click="emit('changeView', 'knowledge')"
        >
          <AppIcon name="grid_view" />
        </button>
        <button
          type="button"
          role="tab"
          class="pdfkb-switcher-tab"
          :class="{ active: activeView === 'chats' }"
          :aria-selected="activeView === 'chats'"
          aria-label="Recent Chats"
          @click="emit('changeView', 'chats')"
        >
          <AppIcon name="chat_bubble" />
        </button>
      </div>

      <section v-if="activeView === 'knowledge'" class="pdfkb-sidebar-panel">
        <div class="pdfkb-section-title">
          <span>Knowledge Base</span>
          <button
            type="button"
            :class="{ active: !selectedContextId }"
            aria-label="Use all PDF sources"
            :aria-pressed="!selectedContextId"
            @click="emit('selectContext', '')"
          >
            <AppIcon name="grid_view" />
          </button>
        </div>

        <div class="pdfkb-tree-list">
          <div v-if="tree.length === 0" class="pdfkb-sidebar-empty">
            <AppIcon name="folder_open" />
            <strong>{{ errorMessage ? 'Unable to load PDF sources' : 'No PDF sources' }}</strong>
            <span>
              {{
                errorMessage ||
                'Upload files from management to build the knowledge base.'
              }}
            </span>
          </div>

          <PdfKnowledgeTreeNode
            v-else
            v-for="node in tree"
            :key="node.id"
            :node="node"
            :depth="0"
            :selected-context-id="selectedContextId"
            @select-context="emit('selectContext', $event)"
          />
        </div>
      </section>

      <PdfRecentChatList
        v-else
        :chats="recentChats"
        :active-session-id="activeSessionId"
        :is-session-loading="isSessionLoading"
        :pending-session-id="pendingSessionId"
        :is-starting-new-chat="isStartingNewChat"
        :is-selection-mode="isChatSelectionMode"
        :is-all-selected="isAllChatsSelected"
        :is-batch-pending="isChatBatchPending"
        :selected-session-ids="selectedSessionIds"
        :busy-session-ids="busySessionIds"
        :error-message="sessionActionError"
        @new-chat="emit('newChat')"
        @open-chat="emit('openChat', $event)"
        @begin-selection="emit('beginChatSelection', $event)"
        @cancel-selection="emit('cancelChatSelection')"
        @toggle-selection="emit('toggleChatSelection', $event)"
        @toggle-select-all="emit('toggleSelectAllChats')"
        @rename-chat="emit('renameChat', $event)"
        @toggle-pinned="emit('toggleChatPinned', $event)"
        @delete-chat="emit('deleteChat', $event)"
        @pin-selected="emit('pinSelectedChats')"
        @unpin-selected="emit('unpinSelectedChats')"
        @delete-selected="emit('deleteSelectedChats')"
      />
    </div>

  </nav>
</template>
