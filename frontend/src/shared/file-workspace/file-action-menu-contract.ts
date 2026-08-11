import type { ActionMenuItem, ActionMenuTone } from './action-menu-contract'
import type { FileActionId } from './file-card-contract'

export type FileActionTone = ActionMenuTone

export interface FileActionItem extends Omit<ActionMenuItem, 'id'> {
  id: FileActionId
}
