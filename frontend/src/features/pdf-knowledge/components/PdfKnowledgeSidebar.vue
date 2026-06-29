<script setup lang="ts">
import AppIcon from '../../../components/AppIcon.vue'
import type { PdfKnowledgeNode, PdfRecentChat, PdfSidebarView } from '../types'

defineProps<{
  activeView: PdfSidebarView
  tree: PdfKnowledgeNode[]
  recentChats: PdfRecentChat[]
}>()

const emit = defineEmits<{
  changeView: [view: PdfSidebarView]
  openManagement: []
  newChat: []
}>()

function iconForNode(node: PdfKnowledgeNode): string {
  if (node.kind === 'pdf') {
    return 'description'
  }
  if (node.kind === 'table') {
    return 'table_chart'
  }
  return node.active ? 'folder_open' : 'folder_open'
}
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

      <section v-if="activeView === 'knowledge'" class="pdfkb-sidebar-panel">
        <div class="pdfkb-section-title">
          <span>Knowledge Base</span>
          <AppIcon name="keyboard_arrow_down" />
        </div>

        <div class="pdfkb-tree-list">
          <div v-if="tree.length === 0" class="pdfkb-sidebar-empty">
            <AppIcon name="folder_open" />
            <strong>No PDF sources</strong>
            <span>Upload files from management to build the knowledge base.</span>
          </div>

          <article
            v-else
            v-for="node in tree"
            :key="node.id"
            class="pdfkb-tree-group"
            :class="{ active: node.active }"
          >
            <button
              type="button"
              class="pdfkb-tree-row"
              :class="{ active: node.active }"
            >
              <AppIcon :name="iconForNode(node)" />
              <span>{{ node.name }}</span>
            </button>

            <div v-if="node.children?.length" class="pdfkb-tree-children">
              <button
                v-for="child in node.children"
                :key="child.id"
                type="button"
                class="pdfkb-tree-row child"
                :class="{ active: child.active }"
              >
                <AppIcon :name="iconForNode(child)" />
                <span>{{ child.name }}</span>
              </button>
            </div>
          </article>
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
        <div class="pdfkb-profile-avatar" aria-hidden="true">RP</div>
        <div class="pdfkb-profile-copy">
          <strong>Research Pro</strong>
          <span>Knowledge Agent</span>
        </div>
        <button type="button" aria-label="Logout unavailable" disabled>
          <AppIcon name="logout" />
        </button>
      </div>
    </div>
  </nav>
</template>
