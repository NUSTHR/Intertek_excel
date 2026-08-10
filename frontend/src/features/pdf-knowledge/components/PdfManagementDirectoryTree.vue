<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AppIcon from '../../../components/AppIcon.vue'
import { PDF_FILES_ROOT_LABEL } from '../../file-library/domain-presentation'
import type { PdfManagedFile, PdfManagedFileKind } from '../types'

interface DirectoryTreeRow {
  id: string
  name: string
  kind: PdfManagedFileKind | 'root'
  depth: number
  childCount: number
  file?: PdfManagedFile
}

const props = defineProps<{
  files: PdfManagedFile[]
  selectedScopeId: string
  selectedFileId: string
}>()

const emit = defineEmits<{
  selectScope: [scopeId: string]
  selectFile: [file: PdfManagedFile]
}>()

const expandedIds = ref<Set<string>>(new Set(['']))

const treeRows = computed<DirectoryTreeRow[]>(() => {
  const fileIds = new Set(props.files.map((file) => file.id))
  const childrenByParent = new Map<string, PdfManagedFile[]>()
  for (const file of props.files) {
    const parentId = file.parentId && fileIds.has(file.parentId) ? file.parentId : ''
    const siblings = childrenByParent.get(parentId) ?? []
    siblings.push(file)
    childrenByParent.set(parentId, siblings)
  }

  const rootRows = flattenRows(childrenByParent, '', 1, new Set<string>())
  return [
    {
      id: '',
      name: PDF_FILES_ROOT_LABEL,
      kind: 'root',
      depth: 0,
      childCount: childrenByParent.get('')?.length ?? 0,
    },
    ...rootRows,
  ]
})

function flattenRows(
  childrenByParent: Map<string, PdfManagedFile[]>,
  parentId: string,
  depth: number,
  visited: Set<string>,
): DirectoryTreeRow[] {
  const rows: DirectoryTreeRow[] = []
  const children = sortTreeFiles(childrenByParent.get(parentId) ?? [])
  for (const child of children) {
    if (visited.has(child.id)) {
      continue
    }
    const nextVisited = new Set(visited)
    nextVisited.add(child.id)
    const childCount = childrenByParent.get(child.id)?.length ?? 0
    rows.push({
      id: child.id,
      name: child.name,
      kind: child.kind,
      depth,
      childCount,
      file: child,
    })
    if (child.kind === 'folder' && expandedIds.value.has(child.id)) {
      rows.push(...flattenRows(childrenByParent, child.id, depth + 1, nextVisited))
    }
  }
  return rows
}

watch(
  () => [props.selectedScopeId, props.selectedFileId, props.files] as const,
  () => {
    const selectedId = props.selectedScopeId || props.selectedFileId
    if (!selectedId) {
      return
    }
    const nextExpanded = new Set(expandedIds.value)
    const fileLookup = new Map(props.files.map((file) => [file.id, file]))
    let current = fileLookup.get(selectedId)
    if (current?.kind !== 'folder') {
      current = current?.parentId ? fileLookup.get(current.parentId) : undefined
    }
    const visited = new Set<string>()
    while (current && !visited.has(current.id)) {
      nextExpanded.add(current.id)
      visited.add(current.id)
      current = current.parentId ? fileLookup.get(current.parentId) : undefined
    }
    expandedIds.value = nextExpanded
  },
  { immediate: true },
)

function sortTreeFiles(files: PdfManagedFile[]): PdfManagedFile[] {
  const kindWeight: Record<PdfManagedFileKind, number> = {
    folder: 0,
    pdf: 1,
    xlsx: 2,
    csv: 3,
  }
  return [...files].sort((left, right) => {
    const kindDelta = kindWeight[left.kind] - kindWeight[right.kind]
    if (kindDelta !== 0) {
      return kindDelta
    }
    return left.name.localeCompare(right.name)
  })
}

function iconForRow(row: DirectoryTreeRow): string {
  if (row.kind === 'root') {
    return 'folder_open'
  }
  if (row.kind === 'folder') {
    return 'folder'
  }
  if (row.kind === 'xlsx') {
    return 'table_rows'
  }
  if (row.kind === 'csv') {
    return 'table_chart'
  }
  return 'picture_as_pdf'
}

function isRowActive(row: DirectoryTreeRow): boolean {
  if (row.kind === 'root' || row.kind === 'folder') {
    return props.selectedScopeId === row.id
  }
  return props.selectedFileId === row.id
}

function rowMeta(row: DirectoryTreeRow): string {
  if (row.kind === 'root') {
    return `${props.files.length}`
  }
  if (row.kind === 'folder') {
    return row.childCount ? `${row.childCount}` : ''
  }
  return ''
}

function disclosureIconForRow(row: DirectoryTreeRow): string {
  if (row.kind !== 'folder') {
    return ''
  }
  if (row.childCount === 0) {
    return 'chevron_right'
  }
  return expandedIds.value.has(row.id) ? 'keyboard_arrow_down' : 'chevron_right'
}

function isExpandable(row: DirectoryTreeRow): boolean {
  return row.kind === 'folder' && row.childCount > 0
}

function toggleFolder(row: DirectoryTreeRow): void {
  if (!isExpandable(row)) {
    return
  }
  const nextExpanded = new Set(expandedIds.value)
  if (nextExpanded.has(row.id)) {
    nextExpanded.delete(row.id)
  } else {
    nextExpanded.add(row.id)
  }
  expandedIds.value = nextExpanded
}

function handleRowClick(row: DirectoryTreeRow): void {
  if (row.kind === 'root' || row.kind === 'folder') {
    emit('selectScope', row.id)
    return
  }
  if (row.file) {
    emit('selectFile', row.file)
  }
}
</script>

<template>
  <section class="pdfmgmt-directory-tree" aria-label="PDF directory tree">
    <div class="pdfmgmt-directory-list">
      <div
        v-for="row in treeRows"
        :key="row.id || 'root'"
        class="pdfmgmt-directory-row"
        :class="[row.kind, { active: isRowActive(row) }]"
        :style="{ '--pdfmgmt-tree-indent': `${row.depth * 14}px` }"
      >
        <button
          v-if="row.kind === 'folder'"
          type="button"
          class="pdfmgmt-directory-toggle"
          :disabled="!isExpandable(row)"
          :aria-label="`${expandedIds.has(row.id) ? 'Collapse' : 'Expand'} ${row.name}`"
          @click.stop="toggleFolder(row)"
        >
          <AppIcon :name="disclosureIconForRow(row)" />
        </button>
        <span
          v-else-if="row.kind !== 'root'"
          class="pdfmgmt-directory-toggle-spacer"
          aria-hidden="true"
        ></span>
        <button
          type="button"
          class="pdfmgmt-directory-select"
          :aria-pressed="isRowActive(row)"
          :title="row.name"
          @click="handleRowClick(row)"
        >
          <AppIcon :name="iconForRow(row)" />
          <span class="pdfmgmt-directory-name">{{ row.name }}</span>
          <small v-if="rowMeta(row)" class="pdfmgmt-directory-meta">{{ rowMeta(row) }}</small>
        </button>
        <button
          v-if="row.kind === 'folder'"
          type="button"
          class="pdfmgmt-directory-action"
          title="Folder Actions"
          disabled
        >
          <AppIcon name="more_vert" />
        </button>
      </div>

      <div v-if="files.length === 0" class="pdfmgmt-directory-empty">
        <AppIcon name="folder_open" />
        <span>No sources yet</span>
      </div>
    </div>
  </section>
</template>
