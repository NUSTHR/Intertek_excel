<script setup lang="ts">
withDefaults(
  defineProps<{
    domain: 'excel' | 'pdf'
    overlayOpen?: boolean
  }>(),
  {
    overlayOpen: false,
  },
)
</script>

<template>
  <section class="file-workspace-source-content" :data-file-domain="domain" :data-domain="domain">
    <slot name="overlay"></slot>

    <div
      class="file-workspace-source-main"
      :inert="overlayOpen ? true : undefined"
    >
      <header class="file-workspace-source-header">
        <slot name="header"></slot>
      </header>

      <div class="file-workspace-source-upload">
        <slot name="upload"></slot>
      </div>

      <div class="file-workspace-source-status">
        <slot name="status"></slot>
      </div>

      <div class="file-workspace-source-list" tabindex="0" aria-label="File list">
        <slot name="list"></slot>
      </div>

      <footer class="file-workspace-source-pagination">
        <slot name="pagination"></slot>
      </footer>
    </div>
  </section>
</template>
