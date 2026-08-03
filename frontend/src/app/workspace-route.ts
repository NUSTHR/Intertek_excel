import type { ActiveView, WorkspaceDestination } from './workspace-types'

const canonicalHashes: Record<WorkspaceDestination, string> = {
  'excel-chat': '#excel-chat',
  'pdf-chat': '#pdf-chat',
  'excel-files': '#excel-files',
  'pdf-files': '#pdf-files',
  'pdf-diagnostics': '#pdf-diagnostics',
}

const hashDestinations = new Map<string, WorkspaceDestination>([
  ...Object.entries(canonicalHashes).map(([destination, hash]) => (
    [hash, destination as WorkspaceDestination] as const
  )),
  ['#chat', 'excel-chat'],
  ['#files', 'excel-files'],
  ['#pdf', 'pdf-files'],
])

export function activeViewFromHash(hash: string): ActiveView {
  return hashDestinations.get(hash) ?? 'excel-chat'
}

export function activeViewHash(view: ActiveView): string {
  return canonicalHashes[view]
}

export function isCanonicalWorkspaceHash(hash: string): boolean {
  return Object.values(canonicalHashes).includes(hash)
}

export function isPdfDestination(view: ActiveView): boolean {
  return view === 'pdf-chat' || view === 'pdf-files' || view === 'pdf-diagnostics'
}

export function isChatDestination(view: ActiveView): boolean {
  return view === 'excel-chat' || view === 'pdf-chat'
}

export function isFileDestination(view: ActiveView): boolean {
  return view === 'excel-files' || view === 'pdf-files'
}

export function canAccessWorkspaceDestination(view: ActiveView, isAdmin: boolean): boolean {
  if (isAdmin) {
    return true
  }
  return view === 'excel-chat' || view === 'pdf-chat'
}

export function defaultWorkspaceDestination(requestedView?: ActiveView): ActiveView {
  return requestedView && isPdfDestination(requestedView) ? 'pdf-chat' : 'excel-chat'
}
