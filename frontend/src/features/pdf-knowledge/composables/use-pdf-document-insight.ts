import { computed, onMounted, ref, watch, type Ref } from 'vue'

import {
  cancelPdfSummaryTask,
  createPdfSummaryTasks,
  generatePdfDocumentSummary,
  getPdfDocumentDetail,
  getPdfSummaryTask,
  listPdfModelSettings,
  retryPdfSummaryTask,
  updatePdfModelSetting,
} from '../../../api/pdf-knowledge-api'
import type {
  PdfDocumentDetail,
  PdfManagementInsightTab,
  PdfManagedFile,
  PdfModelSetting,
  PdfSummaryTask,
} from '../types'
import { usePdfTaskPolling } from './use-pdf-task-polling'

export function usePdfDocumentInsight(
  selectedFile: Ref<PdfManagedFile | undefined>,
  selectedFiles: Readonly<Ref<PdfManagedFile[]>>,
) {
  const summaryTaskPolling = usePdfTaskPolling()
  const activeTab = ref<PdfManagementInsightTab>('summary')
  const documentDetail = ref<PdfDocumentDetail | null>(null)
  const modelSettings = ref<PdfModelSetting[]>([])
  const isDetailLoading = ref<boolean>(false)
  const isSummaryGenerating = ref<boolean>(false)
  const summaryTasks = ref<PdfSummaryTask[]>([])
  const errorMessage = ref<string>('')
  let detailRequestId = 0

  const summary = computed(() => documentDetail.value?.summary ?? null)
  const previewBlocks = computed(() => documentDetail.value?.previewBlocks ?? [])
  const schema = computed(() => documentDetail.value?.schema ?? [])
  const contextTags = computed(() => documentDetail.value?.tags ?? [])
  const parseReport = computed(() => documentDetail.value?.parseReport)

  onMounted(() => {
    void loadModelSettings()
  })

  watch(
    () => {
      const file = selectedFile.value
      return file && file.kind !== 'folder' ? file.id : ''
    },
    (fileId) => {
      if (!fileId) {
        detailRequestId += 1
        documentDetail.value = null
        isDetailLoading.value = false
        return
      }
      void loadDocumentDetail(fileId)
    },
    { immediate: true },
  )

  async function loadDocumentDetail(fileId: string): Promise<void> {
    const requestId = detailRequestId + 1
    detailRequestId = requestId
    isDetailLoading.value = true
    errorMessage.value = ''
    try {
      const detail = await getPdfDocumentDetail(fileId)
      if (requestId !== detailRequestId) {
        return
      }
      documentDetail.value = detail
    } catch (error: unknown) {
      if (requestId === detailRequestId) {
        errorMessage.value = toErrorMessage(error)
      }
    } finally {
      if (requestId === detailRequestId) {
        isDetailLoading.value = false
      }
    }
  }

  async function generateSummary(): Promise<void> {
    const selected = selectedFiles.value
    if (selected.length === 0) {
      return
    }
    const singleFile = selected.length === 1 ? selected[0] : undefined
    isSummaryGenerating.value = true
    errorMessage.value = ''
    summaryTasks.value = []
    summaryTaskPolling.stopPolling()
    try {
      if (singleFile && singleFile.kind !== 'folder') {
        const nextSummary = await generatePdfDocumentSummary(singleFile.id)
        documentDetail.value = {
          ...(documentDetail.value ?? {
            fileId: singleFile.id,
            previewBlocks: [],
            schema: [],
            tags: [],
          }),
          fileId: singleFile.id,
          summary: nextSummary,
        }
        return
      }
      const nextTasks = await createPdfSummaryTasks({
        fileIds: selected.map((file) => file.id),
        includeDescendants: true,
      })
      summaryTasks.value = nextTasks
      startSummaryTaskPolling(nextTasks)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    } finally {
      isSummaryGenerating.value = false
    }
  }

  function startSummaryTaskPolling(tasks: PdfSummaryTask[]): void {
    summaryTaskPolling.stopPolling()
    if (tasks.length === 0 || tasks.every(isTerminalSummaryTask)) {
      return
    }
    const taskIds = tasks.map((task) => task.id)
    summaryTaskPolling.startPolling({
      load: () => Promise.all(taskIds.map(getPdfSummaryTask)),
      isTerminal: (nextTasks) => nextTasks.every(isTerminalSummaryTask),
      onUpdate: (nextTasks) => {
        summaryTasks.value = nextTasks
      },
      onError: (error, isFinalAttempt) => {
        if (isFinalAttempt) {
          errorMessage.value = toErrorMessage(error)
        }
      },
    })
  }

  async function cancelSummaryTask(taskId: string): Promise<void> {
    errorMessage.value = ''
    try {
      const nextTask = await cancelPdfSummaryTask(taskId)
      summaryTasks.value = replaceSummaryTask(summaryTasks.value, nextTask)
      startSummaryTaskPolling(summaryTasks.value)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function retrySummaryTask(taskId: string): Promise<void> {
    errorMessage.value = ''
    try {
      const nextTask = await retryPdfSummaryTask(taskId)
      summaryTasks.value = replaceSummaryTask(summaryTasks.value, nextTask)
      startSummaryTaskPolling(summaryTasks.value)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function loadModelSettings(): Promise<void> {
    try {
      modelSettings.value = await listPdfModelSettings()
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function updateModelPreference(
    settingId: string,
    field: 'selectedProvider' | 'selectedModel',
    value: string,
  ): Promise<void> {
    const currentSetting = modelSettings.value.find((setting) => setting.id === settingId)
    if (!currentSetting) {
      return
    }
    const nextSetting = {
      ...currentSetting,
      [field]: value,
    }
    modelSettings.value = modelSettings.value.map((setting) =>
      setting.id === settingId ? nextSetting : setting,
    )
    errorMessage.value = ''
    try {
      modelSettings.value = await updatePdfModelSetting(settingId, {
        selectedProvider: nextSetting.selectedProvider,
        selectedModel: nextSetting.selectedModel,
      })
    } catch (error: unknown) {
      modelSettings.value = modelSettings.value.map((setting) =>
        setting.id === settingId ? currentSetting : setting,
      )
      errorMessage.value = toErrorMessage(error)
    }
  }

  function setActiveTab(tab: PdfManagementInsightTab): void {
    activeTab.value = tab
  }

  return {
    activeTab,
    documentDetail,
    summary,
    previewBlocks,
    schema,
    contextTags,
    parseReport,
    summaryTasks,
    modelSettings,
    isDetailLoading,
    isSummaryGenerating,
    errorMessage,
    setActiveTab,
    generateSummary,
    cancelSummaryTask,
    retrySummaryTask,
    loadModelSettings,
    updateModelPreference,
  }
}

function isTerminalSummaryTask(task: PdfSummaryTask): boolean {
  return ['ready', 'failed', 'skipped', 'cancelled'].includes(task.status)
}

function replaceSummaryTask(tasks: PdfSummaryTask[], nextTask: PdfSummaryTask): PdfSummaryTask[] {
  return tasks.map((task) => (task.id === nextTask.id ? nextTask : task))
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF insight operation failed.'
}
