<script setup lang="ts">
import { computed, ref } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import type { PdfKnowledgeNode } from '../types'

const props = defineProps<{
  node: PdfKnowledgeNode
  depth: number
  selectedContextId: string
}>()

const emit = defineEmits<{
  selectContext: [fileId: string]
}>()

const isExpanded = ref(true)
const hasChildren = computed(() => Boolean(props.node.children?.length))
const rowPadding = computed(() => `${props.depth * 16}px`)
const childrenId = computed(() => `pdfkb-tree-children-${props.node.id}`)

function iconForNode(node: PdfKnowledgeNode): string {
  if (node.kind === 'pdf') {
    return 'description'
  }
  if (node.kind === 'table') {
    return 'table_chart'
  }
  return 'folder_open'
}

function toggleExpanded(): void {
  if (!hasChildren.value) {
    return
  }
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <article
    class="pdfkb-tree-group"
    :class="{ active: selectedContextId === node.id }"
  >
    <div
      class="pdfkb-tree-row"
      :class="{ active: selectedContextId === node.id, child: depth > 0 }"
      :style="{ '--pdfkb-tree-indent': rowPadding }"
    >
      <button
        v-if="hasChildren"
        type="button"
        class="pdfkb-tree-toggle"
        :aria-expanded="isExpanded"
        :aria-controls="childrenId"
        :aria-label="isExpanded ? `Collapse ${node.name}` : `Expand ${node.name}`"
        @click.stop="toggleExpanded"
      >
        <AppIcon name="chevron_right" />
      </button>
      <span v-else class="pdfkb-tree-toggle-placeholder" aria-hidden="true"></span>
      <button
        type="button"
        class="pdfkb-tree-select"
        :aria-pressed="selectedContextId === node.id"
        @click="emit('selectContext', node.id)"
      >
        <AppIcon :name="iconForNode(node)" />
        <span>{{ node.name }}</span>
      </button>
    </div>

    <div
      v-if="hasChildren && isExpanded"
      :id="childrenId"
      class="pdfkb-tree-children"
    >
      <PdfKnowledgeTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :selected-context-id="selectedContextId"
        @select-context="emit('selectContext', $event)"
      />
    </div>
  </article>
</template>
