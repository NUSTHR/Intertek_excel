<script setup lang="ts">
import AppIcon from '../../components/AppIcon.vue'
import WorkspaceNavigation from '../../components/WorkspaceNavigation.vue'
import type { WorkspaceNavigationItem } from '../../types/workspace-navigation'

defineProps<{
  chatItems: WorkspaceNavigationItem[]
  fileItems: WorkspaceNavigationItem[]
  collapsed: boolean
  isAdmin: boolean
  userEmail: string
  userRoleLabel: string
}>()

const emit = defineEmits<{
  navigate: [itemId: string]
  logout: []
  toggleCollapse: []
}>()
</script>

<template>
  <aside
    class="workspace-global-sidebar"
    :class="{ 'is-collapsed': collapsed }"
    aria-label="Global workspace navigation"
  >
    <div class="workspace-global-brand">
      <span class="workspace-brand-mark" aria-hidden="true">
        <AppIcon name="auto_awesome" />
      </span>
      <div class="workspace-brand-copy">
        <h1>KnowledgeAI</h1>
        <p>Research Workspace</p>
      </div>
    </div>

    <button
      type="button"
      class="workspace-sidebar-toggle"
      :aria-label="collapsed ? 'Expand navigation sidebar' : 'Collapse navigation sidebar'"
      :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      :aria-expanded="!collapsed"
      @click="emit('toggleCollapse')"
    >
      <AppIcon :name="collapsed ? 'chevron_right' : 'chevron_left'" />
    </button>

    <div class="workspace-global-navigation">
      <section class="workspace-navigation-group" aria-labelledby="workspace-chat-nav-label">
        <p id="workspace-chat-nav-label" class="workspace-navigation-label">Chat</p>
        <WorkspaceNavigation
          :items="chatItems"
          variant="global"
          aria-label="Chat workspaces"
          @select="emit('navigate', $event)"
        />
      </section>

      <section
        v-if="fileItems.length"
        class="workspace-navigation-group"
        aria-labelledby="workspace-file-nav-label"
      >
        <p id="workspace-file-nav-label" class="workspace-navigation-label">Files</p>
        <WorkspaceNavigation
          :items="fileItems"
          variant="global"
          aria-label="File workspaces"
          @select="emit('navigate', $event)"
        />
      </section>
    </div>

    <div class="workspace-global-footer">
      <button type="button" class="workspace-global-support" disabled title="Support">
        <span class="workspace-global-nav__icon"><AppIcon name="help" /></span>
        <span class="workspace-global-nav__label">Support</span>
      </button>
      <div class="workspace-global-user">
        <div class="workspace-global-avatar" :class="{ admin: isAdmin }" aria-hidden="true">
          <AppIcon :name="isAdmin ? 'verified' : 'user'" />
        </div>
        <div class="workspace-user-copy">
          <strong>{{ userRoleLabel }}</strong>
          <span>{{ userEmail }}</span>
        </div>
        <button
          type="button"
          class="workspace-global-logout"
          aria-label="Logout"
          title="Logout"
          @click="emit('logout')"
        >
          <AppIcon name="logout" />
        </button>
      </div>
    </div>
  </aside>
</template>
