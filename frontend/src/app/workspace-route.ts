import type { ActiveView } from './workspace-types'

export function activeViewFromHash(hash: string): ActiveView {
  if (hash === '#files') {
    return 'files'
  }
  if (hash === '#pdf') {
    return 'pdf'
  }
  if (hash === '#pdf-diagnostics') {
    return 'pdf-diagnostics'
  }
  return 'chat'
}

export function activeViewHash(view: ActiveView): string {
  return `#${view}`
}
