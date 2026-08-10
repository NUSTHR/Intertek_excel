<script setup lang="ts" generic="T extends string">
defineProps<{
  activeTab: T
  tabs: Array<{ key: T; label: string }>
}>()

const emit = defineEmits<{
  change: [tab: T]
}>()
</script>

<template>
  <button
    v-for="tab in tabs"
    :key="tab.key"
    type="button"
    class="file-workspace-base-insight-tab"
    role="tab"
    :data-active="activeTab === tab.key"
    :aria-selected="activeTab === tab.key"
    @click="emit('change', tab.key)"
  >
    {{ tab.label }}
  </button>
</template>
