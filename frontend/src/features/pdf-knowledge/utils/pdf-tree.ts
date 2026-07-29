import type { PdfKnowledgeNode, PdfManagedFile } from '../types'

export function buildPdfKnowledgeTree(files: PdfManagedFile[]): PdfKnowledgeNode[] {
  const fileIds = new Set(files.map((file) => file.id))
  const childrenByParent = new Map<string, PdfManagedFile[]>()
  for (const file of files) {
    const parentId = (
      file.parentId &&
      file.parentId !== file.id &&
      fileIds.has(file.parentId)
    )
      ? file.parentId
      : ''
    const children = childrenByParent.get(parentId) ?? []
    children.push(file)
    childrenByParent.set(parentId, children)
  }

  const visited = new Set<string>()
  const roots = toNodes(childrenByParent, '', visited)
  for (const file of files) {
    if (!visited.has(file.id)) {
      const node = toNode(file, childrenByParent, visited)
      if (node) {
        roots.push(node)
      }
    }
  }
  return roots
}

function toNodes(
  childrenByParent: Map<string, PdfManagedFile[]>,
  parentId: string,
  visited: Set<string>,
): PdfKnowledgeNode[] {
  return (childrenByParent.get(parentId) ?? [])
    .map((file) => toNode(file, childrenByParent, visited))
    .filter((node): node is PdfKnowledgeNode => Boolean(node))
}

function toNode(
  file: PdfManagedFile,
  childrenByParent: Map<string, PdfManagedFile[]>,
  visited: Set<string>,
): PdfKnowledgeNode | null {
  if (visited.has(file.id)) {
    return null
  }
  visited.add(file.id)
  const children = toNodes(childrenByParent, file.id, visited)
  return {
    id: file.id,
    name: file.name,
    kind: file.kind === 'pdf' ? 'pdf' : file.kind === 'folder' ? 'folder' : 'table',
    children: children.length > 0 ? children : undefined,
  }
}
