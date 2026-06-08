<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  name: string
}>()

const iconPaths: Record<string, string[]> = {
  add: ['M12 5v14M5 12h14'],
  add_chart: ['M4 19V5M4 19h16', 'M8 16v-4M12 16V9M16 16v-7', 'M18 4v4M16 6h4'],
  analytics: ['M4 19V5M4 19h16M8 16v-5M12 16V8M16 16v-8M20 16v-3'],
  arrow_upward: ['M12 19V5M6 11l6-6 6 6'],
  attach_file: ['M8 13l6.4-6.4a3 3 0 014.2 4.2l-8 8a5 5 0 01-7.1-7.1l7.6-7.6'],
  auto_awesome: ['M12 3l1.7 5.1L19 10l-5.3 1.9L12 17l-1.7-5.1L5 10l5.3-1.9L12 3z', 'M19 3v4M17 5h4M5 17v4M3 19h4'],
  bolt: ['M13 2L4 14h7l-1 8 9-12h-7l1-8z'],
  chat_bubble: ['M5 6.5A3.5 3.5 0 018.5 3h7A3.5 3.5 0 0119 6.5v5A3.5 3.5 0 0115.5 15H11l-5 4v-4.2A3.5 3.5 0 015 11.5v-5z'],
  chevron_left: ['M15 18l-6-6 6-6'],
  chevron_right: ['M9 6l6 6-6 6'],
  close: ['M6 6l12 12M18 6L6 18'],
  dashboard: ['M4 5h7v7H4V5zM13 5h7v4h-7V5zM13 11h7v8h-7v-8zM4 14h7v5H4v-5z'],
  description: ['M7 3h7l5 5v13H7V3z', 'M14 3v6h5', 'M9 13h6M9 17h6'],
  download: ['M12 3v11M7 9l5 5 5-5', 'M5 19h14'],
  edit: ['M4 20h4l11-11a2.8 2.8 0 00-4-4L4 16v4z', 'M13.5 6.5l4 4'],
  folder_open: ['M3 7h7l2 2h9l-2 10H5L3 7z', 'M3 7V5h6l2 2'],
  fullscreen: ['M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5'],
  close_fullscreen: ['M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5'],
  fullscreen_exit: ['M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5'],
  grid_view: ['M4 4h6v6H4V4zM14 4h6v6h-6V4zM4 14h6v6H4v-6zM14 14h6v6h-6v-6z'],
  help: ['M12 20h.01', 'M9.5 9a2.5 2.5 0 115 0c0 2.5-2.5 2.2-2.5 5', 'M12 22a10 10 0 100-20 10 10 0 000 20z'],
  history: ['M3 12a9 9 0 109-9', 'M3 5v7h7', 'M12 7v5l4 2'],
  keyboard_arrow_down: ['M6 9l6 6 6-6'],
  logout: ['M10 6H6v12h4', 'M14 8l4 4-4 4', 'M18 12H9'],
  more_vert: ['M12 7h.01M12 12h.01M12 17h.01'],
  notifications: ['M18 16H6l1.4-2.4V10a4.6 4.6 0 119.2 0v3.6L18 16z', 'M10 19a2 2 0 004 0'],
  query_stats: ['M4 19V5M4 19h16', 'M7 15l3-4 3 2 5-7', 'M18 6h2v2'],
  refresh: ['M20 6v5h-5', 'M4 18v-5h5', 'M19 11a7 7 0 00-12-4M5 13a7 7 0 0012 4'],
  schema: ['M12 3v5M6 11h12M6 11v5M18 11v5', 'M9 8h6v6H9V8z', 'M3 16h6v5H3v-5z', 'M15 16h6v5h-6v-5z'],
  search: ['M11 18a7 7 0 100-14 7 7 0 000 14z', 'M16 16l4 4'],
  settings: ['M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7z', 'M19 13.5v-3l-2.1-.5a7 7 0 00-.7-1.7l1.1-1.8-2.1-2.1-1.8 1.1a7 7 0 00-1.7-.7L11.5 3h-3l-.5 2.1a7 7 0 00-1.7.7L4.5 4.7 2.4 6.8l1.1 1.8a7 7 0 00-.7 1.7L1 10.5v3l2.1.5a7 7 0 00.7 1.7l-1.1 1.8 2.1 2.1 1.8-1.1a7 7 0 001.7.7l.5 2.1h3l.5-2.1a7 7 0 001.7-.7l1.8 1.1 2.1-2.1-1.1-1.8a7 7 0 00.7-1.7l1.5-.5z'],
  table_chart: ['M4 5h16v14H4V5z', 'M4 10h16M9 5v14M15 5v14'],
  table_rows: ['M4 5h16v14H4V5z', 'M4 10h16M4 14h16'],
  tune: ['M4 7h10M18 7h2M4 17h2M10 17h10', 'M14 5v4M8 15v4'],
  view_week: ['M4 5h16v14H4V5z', 'M9 5v14M15 5v14'],
}

const paths = computed(() => iconPaths[props.name] ?? iconPaths.description)
</script>

<template>
  <svg
    class="app-icon"
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
  >
    <path v-for="path in paths" :key="path" :d="path" />
  </svg>
</template>
