import type { FileWorkspaceIconName } from './file-card-contract'

export type ActionMenuTone = 'default' | 'danger'

export interface ActionMenuItem {
  id: string
  label: string
  iconName: FileWorkspaceIconName
  tone?: ActionMenuTone
  disabled?: boolean
}

