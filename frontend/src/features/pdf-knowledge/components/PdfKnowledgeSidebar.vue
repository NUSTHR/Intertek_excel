<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { PdfKnowledgeNode, PdfRecentChat, PdfSidebarView } from '../types'
import PdfKnowledgeTreeNode from './PdfKnowledgeTreeNode.vue'

defineProps<{
  activeView: PdfSidebarView
  errorMessage: string
  selectedContextId: string
  isAdmin: boolean
  tree: PdfKnowledgeNode[]
  recentChats: PdfRecentChat[]
  userEmail: string
  userRoleLabel: string
}>()

const emit = defineEmits<{
  changeView: [view: PdfSidebarView]
  openManagement: []
  newChat: []
  openChat: [chatId: string]
  selectContext: [fileId: string]
}>()

</script>

<template>
  <nav class="pdfkb-sidebar" aria-label="PDF knowledge navigation">
    <div class="pdfkb-brand-block">
      <div class="pdfkb-brand-mark">
        <AppIcon name="description" />
      </div>
      <span>PDF AI</span>
    </div>

    <div class="pdfkb-sidebar-cta">
      <button type="button" class="pdfkb-new-chat" @click="emit('newChat')">
        <AppIcon name="chat_bubble" />
        <span>New Chat</span>
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

      <div class="pdfkb-mobile-actions">
        <button type="button" @click="emit('openManagement')">
          <AppIcon name="folder_open" />
          <span>Manage Files</span>
        </button>
      </div>

      <section v-if="activeView === 'knowledge'" class="pdfkb-sidebar-panel">
        <div class="pdfkb-section-title">
          <span>Knowledge Base</span>
          <button
            type="button"
            :class="{ active: !selectedContextId }"
            aria-label="Use all PDF sources"
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

      <section v-else class="pdfkb-sidebar-panel pdfkb-chat-list-panel">
        <div class="pdfkb-section-title">
          <span>Recent Chats</span>
          <button type="button" aria-label="Add chat unavailable" disabled>
            <AppIcon name="add" />
          </button>
        </div>

        <div class="pdfkb-recent-chat-list">
          <div v-if="recentChats.length === 0" class="pdfkb-sidebar-empty">
            <AppIcon name="chat_bubble" />
            <strong>No recent chats</strong>
            <span>Start a PDF chat to keep history here.</span>
          </div>

          <button
            v-else
            v-for="chat in recentChats"
            :key="chat.id"
            type="button"
            class="pdfkb-recent-chat"
            @click="emit('openChat', chat.id)"
          >
            <AppIcon name="chat_bubble" />
            <span>{{ chat.title }}</span>
          </button>
        </div>
      </section>
    </div>

    <div class="pdfkb-sidebar-footer">
      <div class="pdfkb-footer-links">
        <button type="button" disabled>
          <AppIcon name="settings" />
          <span>Settings</span>
        </button>
        <button type="button" @click="emit('openManagement')">
          <AppIcon name="folder_open" />
          <span>Manage Files</span>
        </button>
        <button type="button" disabled>
          <AppIcon name="help" />
          <span>Support Center</span>
        </button>
      </div>

      <div class="pdfkb-profile">
        <div class="pdfkb-profile-avatar" :class="{ admin: isAdmin }" aria-hidden="true">
          <AppIcon :name="isAdmin ? 'verified' : 'user'" />
        </div>
        <div class="pdfkb-profile-copy">
          <strong>{{ userEmail }}</strong>
          <span>{{ userRoleLabel }}</span>
        </div>
        <button type="button" aria-label="Logout unavailable" disabled>
          <AppIcon name="logout" />
        </button>
      </div>
    </div>
  </nav>
</template>
