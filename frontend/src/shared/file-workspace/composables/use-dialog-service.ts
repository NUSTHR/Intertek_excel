import { inject, provide, ref, type InjectionKey, type Ref } from 'vue'

import type {
  DeleteTarget,
  DialogResult,
  GenericDialog,
  RenameTarget,
  UploadContext,
} from '../dialog-contract'
import type { UploadTaskViewModel } from '../upload-task-contract'

/**
 * Centralised dialog state. A single instance is provided at the
 * application root and consumed by both Excel and PDF surfaces, so the
 * host component (`WorkspaceDialogs`) can render any of the three
 * supported payloads (`rename` / `delete` / `upload`) regardless of which
 * domain triggered the dialog.
 *
 * The composable returns a reactive `current` ref; the renderer reads
 * from it and dispatches back through `submitRename` / `confirmDelete` /
 * `confirmUpload` / `close`. The optional `resolver` field lets callers
 * `await` user action through `await open(...)`, which simplifies the
 * domain code paths.
 */
export interface DialogService {
  current: Ref<GenericDialog | null>
  open: (next: GenericDialog) => Promise<DialogResult>
  close: () => void
  setError: (message: string) => void
  setBusy: (busy: boolean) => void
  setRenameDraft: (draft: string) => void
  submitRename: (draft: string) => void
  confirmDelete: () => void
  confirmUpload: () => void
  /** @internal Used by tests to reset state between scenarios. */
  __reset: () => void
}

export const DIALOG_SERVICE_KEY: InjectionKey<DialogService> = Symbol('DialogService')

export function provideDialogService(): DialogService {
  const service = createDialogService()
  provide(DIALOG_SERVICE_KEY, service)
  return service
}

export function useDialogService(): DialogService {
  const service = inject(DIALOG_SERVICE_KEY, null)
  if (!service) {
    throw new Error(
      'useDialogService() called outside a provideDialogService() tree. '
        + 'Wrap the consuming component in a parent that calls provideDialogService().',
    )
  }
  return service
}

export function useOptionalDialogService(): DialogService | null {
  return inject(DIALOG_SERVICE_KEY, null)
}

export function createDialogService(): DialogService {
  const current = ref<GenericDialog | null>(null)
  let resolver: ((result: DialogResult) => void) | null = null

  function open(next: GenericDialog): Promise<DialogResult> {
    if (current.value) {
      // The previously open dialog is being preempted; resolve the
      // previous caller's promise as a cancel for the *previous* kind
      // (not the new one) so the awaiting caller can roll back the
      // right action.
      resolver?.(cancelResultFor(current.value))
    }
    current.value = next
    return new Promise<DialogResult>((resolve) => {
      resolver = resolve
    })
  }

  function close(): void {
    if (!current.value) {
      return
    }
    const result = cancelResultFor(current.value)
    current.value = null
    resolver?.(result)
    resolver = null
  }

  function setError(message: string): void {
    if (!current.value) {
      return
    }
    current.value = withError(current.value, message)
  }

  function setBusy(busy: boolean): void {
    if (!current.value) {
      return
    }
    current.value = { ...current.value, isBusy: busy }
  }

  function setRenameDraft(draft: string): void {
    if (!current.value || current.value.kind !== 'rename') {
      return
    }
    current.value = { ...current.value, draft, errorMessage: '' }
  }

  function submitRename(draft: string): void {
    if (!current.value || current.value.kind !== 'rename') {
      return
    }
    const trimmed = draft.trim()
    if (!trimmed) {
      setError('Name cannot be empty.')
      return
    }
    const result: DialogResult = { kind: 'rename', action: 'submit', draft: trimmed }
    current.value = null
    resolver?.(result)
    resolver = null
  }

  function confirmDelete(): void {
    if (!current.value || current.value.kind !== 'delete') {
      return
    }
    const result: DialogResult = { kind: 'delete', action: 'confirm' }
    current.value = null
    resolver?.(result)
    resolver = null
  }

  function confirmUpload(): void {
    if (!current.value || current.value.kind !== 'upload') {
      return
    }
    const result: DialogResult = { kind: 'upload', action: 'confirm' }
    current.value = null
    resolver?.(result)
    resolver = null
  }

  function __reset(): void {
    resolver?.(cancelResultFor(current.value))
    resolver = null
    current.value = null
  }

  return { current, open, close, setError, setBusy, setRenameDraft, submitRename, confirmDelete, confirmUpload, __reset }
}

function cancelResultFor(dialog: GenericDialog | null): DialogResult {
  if (!dialog) {
    return { kind: 'delete', action: 'cancel' }
  }
  if (dialog.kind === 'rename') {
    return { kind: 'rename', action: 'cancel' }
  }
  if (dialog.kind === 'delete') {
    return { kind: 'delete', action: 'cancel' }
  }
  return { kind: 'upload', action: 'cancel' }
}

function withError(dialog: GenericDialog, message: string): GenericDialog {
  return { ...dialog, errorMessage: message }
}

/* ------------------------------------------------------------------ *
 * Helper builders so feature code does not assemble GenericDialog
 * payloads inline.
 * ------------------------------------------------------------------ */

export function buildRenameDialog(
  target: RenameTarget,
  draft: string,
  isBusy = false,
): GenericDialog {
  return { kind: 'rename', target, draft, isBusy, errorMessage: '' }
}

export function buildDeleteDialog(
  target: DeleteTarget,
  isBusy = false,
): GenericDialog {
  return { kind: 'delete', target, isBusy, errorMessage: '' }
}

export function buildUploadDialog(
  context: UploadContext,
  task: UploadTaskViewModel | null = null,
  isBusy = false,
): GenericDialog {
  return { kind: 'upload', context, task, isBusy, errorMessage: '' }
}
