import type { FileDomain } from './file-card-contract'

export interface BaseDropzoneProps {
  accept: string
  multiple: boolean
  helpText: string
  isDisabled: boolean
  maxSizeBytes: number
  domain: FileDomain
  promptLabel: string
}

export interface BaseDropzoneEmits {
  filesSelected: [files: File[]]
  validationError: [message: string]
  pickerOpened: []
}

/**
 * Error codes surfaced by `validateDropzoneFiles` so callers can show the
 * appropriate translation / tone without re-parsing strings.
 */
export type DropzoneValidationErrorCode =
  | 'too-many-files'
  | 'extension-mismatch'
  | 'file-too-large'
  | 'empty-file'

export interface DropzoneValidationError {
  code: DropzoneValidationErrorCode
  message: string
  fileName?: string
}
