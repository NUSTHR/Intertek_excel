<script setup lang="ts">
import { computed } from 'vue'

import { appIconPaths } from './app-icons'

const props = defineProps<{
  name: string
}>()

const paths = computed(() => appIconPaths[props.name] ?? appIconPaths.description)
</script>

<template>
  <svg
    class="app-icon"
    aria-hidden="true"
    viewBox="0 0 24 24"
    preserveAspectRatio="xMidYMid meet"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    vector-effect="non-scaling-stroke"
  >
    <path
      v-for="path in paths"
      :key="path"
      :d="path"
      vector-effect="non-scaling-stroke"
    />
  </svg>
</template>
