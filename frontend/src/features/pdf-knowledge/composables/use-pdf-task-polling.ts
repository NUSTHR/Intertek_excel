import { onBeforeUnmount } from 'vue'

interface PdfTaskPollingOptions<T> {
  load: () => Promise<T>
  isTerminal: (value: T) => boolean
  onUpdate?: (value: T) => void
  onTerminal?: (value: T) => void | Promise<void>
  onError?: (error: unknown, isFinalAttempt: boolean) => void
  intervalMs?: number
  maxConsecutiveErrors?: number
}

const defaultIntervalMs = 1100
const defaultMaxConsecutiveErrors = 3

export function usePdfTaskPolling() {
  let timer: number | null = null
  let generation = 0

  function stopPolling(): void {
    generation += 1
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function startPolling<T>(options: PdfTaskPollingOptions<T>): void {
    stopPolling()
    const currentGeneration = generation
    let consecutiveErrors = 0

    const poll = async (): Promise<void> => {
      if (currentGeneration !== generation) {
        return
      }
      try {
        const value = await options.load()
        if (currentGeneration !== generation) {
          return
        }
        consecutiveErrors = 0
        options.onUpdate?.(value)
        if (options.isTerminal(value)) {
          timer = null
          await options.onTerminal?.(value)
          return
        }
      } catch (error: unknown) {
        if (currentGeneration !== generation) {
          return
        }
        consecutiveErrors += 1
        const isFinalAttempt =
          consecutiveErrors >=
          (options.maxConsecutiveErrors ?? defaultMaxConsecutiveErrors)
        options.onError?.(error, isFinalAttempt)
        if (isFinalAttempt) {
          timer = null
          return
        }
      }
      timer = window.setTimeout(
        () => void poll(),
        options.intervalMs ?? defaultIntervalMs,
      )
    }

    void poll()
  }

  onBeforeUnmount(stopPolling)

  return {
    startPolling,
    stopPolling,
  }
}
