export interface CoordinatedRequest {
  readonly id: number
  readonly signal: AbortSignal
  isCurrent: () => boolean
}

export interface RequestCoordinator {
  begin: () => CoordinatedRequest
  cancel: () => void
}

export function createRequestCoordinator(): RequestCoordinator {
  let revision = 0
  let activeController: AbortController | null = null

  function begin(): CoordinatedRequest {
    activeController?.abort()
    const controller = new AbortController()
    const id = ++revision
    activeController = controller
    return {
      id,
      signal: controller.signal,
      isCurrent: () => (
        id === revision &&
        activeController === controller &&
        !controller.signal.aborted
      ),
    }
  }

  function cancel(): void {
    revision += 1
    activeController?.abort()
    activeController = null
  }

  return {
    begin,
    cancel,
  }
}
