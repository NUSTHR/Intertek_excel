import type { FileDomain } from './file-card-contract'
import type { UploadTaskViewModel } from './upload-task-contract'

/**
 * `GenericDialog` is the unified dialog state used by `WorkspaceDialogs`.
 * Every dialog payload is a discriminated union so the renderer can switch on
 * `kind` exhaustively. Domain layers must use these shapes — no inline
 * `dialog-backdrop` may live outside the central host.
 */
export type DialogTargetDomain = FileDomain | 'chat-session'

/** Presentation-only target. Domain records stay inside their features. */
export interface DialogTarget {
  domain: DialogTargetDomain
  id: string
  displayName: string
  kindLabel: string
  dependentHint?: string
}

export type RenameTarget = DialogTarget

export type DeleteTarget = DialogTarget

export type UploadContext = {
  domain: FileDomain
  file: { name: string; sizeBytes: number }
  kind: 'new' | 'replace'
  scopeLabel?: string
}

export type GenericDialog =
  | {
      kind: 'rename'
      target: RenameTarget
      draft: string
      isBusy: boolean
      errorMessage: string
    }
  | {
      kind: 'delete'
      target: DeleteTarget
      isBusy: boolean
      errorMessage: string
    }
  | {
      kind: 'upload'
      context: UploadContext
      task: UploadTaskViewModel | null
      isBusy: boolean
      errorMessage: string
    }

export type DialogResult =
  | { kind: 'rename'; action: 'submit'; draft: string }
  | { kind: 'rename'; action: 'cancel' }
  | { kind: 'delete'; action: 'confirm' }
  | { kind: 'delete'; action: 'cancel' }
  | { kind: 'upload'; action: 'confirm' }
  | { kind: 'upload'; action: 'cancel' }
