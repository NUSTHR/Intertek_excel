<script setup lang="ts">
defineProps<{
  title: string
  countLabel: string
}>()
</script>

<template>
  <div class="file-workspace-base-list-heading">
    <div class="file-workspace-base-list-heading-title">
      <h3>{{ title }}</h3>
      <slot name="navigation"></slot>
    </div>
    <span>{{ countLabel }}</span>
  </div>
</template>
