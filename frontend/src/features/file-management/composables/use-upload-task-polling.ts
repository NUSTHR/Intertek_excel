import { computed, onBeforeUnmount, ref } from 'vue'

import { getUploadTask } from '../../../api/excel-assets-api'

import type { UploadTaskResponse } from '../../../types/excel-assets'

type UploadTaskReadyHandler = (task: UploadTaskResponse) => Promise<void> | void
type UploadTaskFailureHandler = (message: string, task: UploadTaskResponse) => void
type UploadTaskErrorHandler = (error: unknown) => void

type UploadTaskPollingHandlers = {
  isCurrent: () => boolean
  onReady: UploadTaskReadyHandler
  onFailure: UploadTaskFailureHandler
  onError: UploadTaskErrorHandler
}

type UploadTaskPollingOptions = {
  pollIntervalMs?: number
}

const defaultPollIntervalMs = 900

export function useUploadTaskPolling(options: UploadTaskPollingOptions = {}) {
  const uploadTask = ref<UploadTaskResponse | null>(null)
  const pollIntervalMs = Math.max(250, options.pollIntervalMs ?? defaultPollIntervalMs)
  let pollTimer: number | null = null

  const isUploadTaskPending = computed(() => {
    return uploadTask.value?.status === 'queued' || uploadTask.value?.status === 'processing'
  })

  function setUploadTask(task: UploadTaskResponse | null): void {
    uploadTask.value = task
  }

  function clearUploadTask(): void {
    stopUploadTaskPolling()
    uploadTask.value = null
  }

  function stopUploadTaskPolling(): void {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function pollUploadTask(
    taskId: string,
    handlers: UploadTaskPollingHandlers,
  ): Promise<void> {
    stopUploadTaskPolling()
    await refreshUploadTask(taskId, handlers)
  }

  async function refreshUploadTask(
    taskId: string,
    handlers: UploadTaskPollingHandlers,
  ): Promise<void> {
    try {
      const task = await getUploadTask(taskId)
      if (!handlers.isCurrent()) {
        return
      }
      uploadTask.value = task
      if (task.status === 'ready') {
        if (task.result) {
          await handlers.onReady(task)
          return
        }
        handlers.onError(
          new Error('Workbook parsing completed, but the result is unavailable. Refresh and try again.'),
        )
        return
      }
      if (task.status === 'failed') {
        handlers.onFailure(task.error_message || 'Workbook parsing failed.', task)
        return
      }
      pollTimer = window.setTimeout(() => {
        void refreshUploadTask(taskId, handlers)
      }, pollIntervalMs)
    } catch (error: unknown) {
      if (handlers.isCurrent()) {
        handlers.onError(error)
      }
    }
  }

  onBeforeUnmount(() => {
    stopUploadTaskPolling()
  })

  return {
    uploadTask,
    isUploadTaskPending,
    setUploadTask,
    clearUploadTask,
    pollUploadTask,
    stopUploadTaskPolling,
  }
}
