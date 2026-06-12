import { ref } from 'vue'

import type { FeedbackMessage, FeedbackTone } from './workspace-types'

export function useTransientFeedback(defaultDurationMs: number) {
  const feedback = ref<FeedbackMessage | null>(null)
  let timer: number | null = null

  function show(tone: FeedbackTone, message: string, durationMs = defaultDurationMs): void {
    feedback.value = { tone, message }
    if (timer !== null) {
      window.clearTimeout(timer)
    }
    timer = window.setTimeout(() => {
      feedback.value = null
      timer = null
    }, durationMs)
  }

  function clear(): void {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
    feedback.value = null
  }

  return {
    feedback,
    show,
    clear,
  }
}
