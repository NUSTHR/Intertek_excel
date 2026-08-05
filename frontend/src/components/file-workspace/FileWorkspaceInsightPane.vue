<script setup lang="ts">
withDefaults(
  defineProps<{
    domain: 'excel' | 'pdf'
    fullscreen?: boolean
  }>(),
  {
    fullscreen: false,
  },
)
</script>

<template>
  <section
    class="file-workspace-insight-content file-insight-pane"
    :class="{ fullscreen, 'pdfmgmt-insight-pane': domain === 'pdf' }"
  >
    <header
      class="file-workspace-insight-tabs file-insight-tabs"
      :class="{ 'pdfmgmt-insight-tabs': domain === 'pdf' }"
    >
      <div class="file-workspace-insight-tab-list" role="tablist">
        <slot name="tabs"></slot>
      </div>
      <div class="file-workspace-insight-tools file-insight-tools">
        <slot name="actions"></slot>
      </div>
    </header>

    <div
      class="file-workspace-insight-scroll file-insight-scroll"
      :class="{ 'pdfmgmt-insight-scroll': domain === 'pdf' }"
    >
      <slot></slot>
    </div>
  </section>
</template>
