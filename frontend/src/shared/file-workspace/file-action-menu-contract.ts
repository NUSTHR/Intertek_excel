import type { FileActionId, FileWorkspaceIconName } from './file-card-contract'

export type FileActionTone = 'default' | 'danger'

export interface FileActionItem {
  id: FileActionId
  label: string
  iconName: FileWorkspaceIconName
  tone?: FileActionTone
  disabled?: boolean
}

export interface BaseFileActionMenuProps {
  isOpen: boolean
  items: FileActionItem[]
  anchor: 'left' | 'right'
  isDisabled: boolean
}

export interface BaseFileActionMenuEmits {
  select: [action: FileActionId]
  close: []
}
