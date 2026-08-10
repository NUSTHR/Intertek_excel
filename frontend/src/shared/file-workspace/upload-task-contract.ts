export type UploadTaskStage =
  | 'queued'
  | 'claimed'
  | 'parsing'
  | 'indexing'
  | 'processing'
  | 'ready'
  | 'failed'
  | 'cancelled'

export type UploadTaskStatus =
  | 'queued'
  | 'processing'
  | 'ready'
  | 'failed'
  | 'cancelled'

/**
 * Cross-domain upload task view model. Both Excel and PDF adapt their
 * native task records into this shape; the insight composable (`useInsightUploadTask`)
 * is the only consumer that knows about it.
 */
export interface UploadTaskViewModel {
  taskId: string
  status: UploadTaskStatus
  stage: UploadTaskStage
  progress: number
  message: string
  isTerminal: boolean
  errorMessage?: string
  fileId?: string
  fileName?: string
}

export interface UploadTaskPollingHooks {
  onUpdate?: (tasks: UploadTaskViewModel[]) => void
  onTerminal?: (tasks: UploadTaskViewModel[]) => void
  onError?: (error: unknown, isFinalAttempt: boolean) => void
}
