import { computed, onMounted, ref, watch, type Ref } from 'vue'

import {
  cancelPdfSummaryTask,
  createPdfSummaryTasks,
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
  PdfModelSettingFieldErrors,
  PdfSummaryTask,
} from '../types'
import {
  hasPdfModelSettingErrors,
  validatePdfModelSetting,
} from '../utils/pdf-model-setting'
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
  const modelSettingErrors = ref<Record<string, PdfModelSettingFieldErrors>>({})
  const errorMessage = ref<string>('')
  let detailRequestId = 0
  let summaryOperationId = 0
  let modelSettingsRevision = 0
  let modelSettingsLoadRequestId = 0
  const modelSettingMutationIds = new Map<string, number>()
  const modelSettingSaveChains = new Map<string, Promise<void>>()

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
      invalidateSummaryOperation()
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

  watch(
    () => selectedFiles.value.map((file) => file.id).sort().join('|'),
    () => {
      invalidateSummaryOperation()
    },
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
    const selected = [...selectedFiles.value]
    if (selected.length === 0) {
      return
    }
    const operationId = ++summaryOperationId
    const targetFileIds = selected.map((file) => file.id)
    isSummaryGenerating.value = true
    errorMessage.value = ''
    summaryTasks.value = []
    summaryTaskPolling.stopPolling()
    try {
      const nextTasks = await createPdfSummaryTasks({
        fileIds: targetFileIds,
        includeDescendants: true,
      })
      if (operationId !== summaryOperationId) {
        return
      }
      summaryTasks.value = nextTasks
      startSummaryTaskPolling(nextTasks, operationId, targetFileIds)
    } catch (error: unknown) {
      if (operationId === summaryOperationId) {
        errorMessage.value = toErrorMessage(error)
      }
    } finally {
      if (operationId === summaryOperationId) {
        isSummaryGenerating.value = false
      }
    }
  }

  function startSummaryTaskPolling(
    tasks: PdfSummaryTask[],
    operationId = summaryOperationId,
    targetFileIds = tasks.map((task) => task.fileId),
  ): void {
    summaryTaskPolling.stopPolling()
    if (tasks.length === 0 || tasks.every(isTerminalSummaryTask)) {
      void refreshSummaryTarget(operationId, targetFileIds)
      return
    }
    const taskIds = tasks.map((task) => task.id)
    summaryTaskPolling.startPolling({
      load: () => Promise.all(taskIds.map(getPdfSummaryTask)),
      isTerminal: (nextTasks) => nextTasks.every(isTerminalSummaryTask),
      onUpdate: (nextTasks) => {
        if (operationId === summaryOperationId) {
          summaryTasks.value = nextTasks
        }
      },
      onTerminal: () => refreshSummaryTarget(operationId, targetFileIds),
      onError: (error, isFinalAttempt) => {
        if (isFinalAttempt && operationId === summaryOperationId) {
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
      startSummaryTaskPolling(summaryTasks.value, summaryOperationId)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function retrySummaryTask(taskId: string): Promise<void> {
    errorMessage.value = ''
    try {
      const nextTask = await retryPdfSummaryTask(taskId)
      summaryTasks.value = replaceSummaryTask(summaryTasks.value, nextTask)
      startSummaryTaskPolling(summaryTasks.value, summaryOperationId)
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    }
  }

  async function loadModelSettings(): Promise<void> {
    const requestId = ++modelSettingsLoadRequestId
    const startingRevision = modelSettingsRevision
    try {
      const settings = await listPdfModelSettings()
      if (
        requestId === modelSettingsLoadRequestId &&
        startingRevision === modelSettingsRevision
      ) {
        modelSettings.value = settings
        modelSettingErrors.value = Object.fromEntries(
          settings.map((setting) => [setting.id, validatePdfModelSetting(setting)]),
        )
      }
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
    let nextSetting = {
      ...currentSetting,
      [field]: value,
    }
    if (field === 'selectedProvider') {
      const supportedModels = nextSetting.providerModels?.[value] ?? []
      if (!supportedModels.includes(nextSetting.selectedModel)) {
        nextSetting = {
          ...nextSetting,
          selectedModel: supportedModels[0] ?? '',
        }
      }
    }
    modelSettings.value = modelSettings.value.map((setting) =>
      setting.id === settingId ? nextSetting : setting,
    )
    errorMessage.value = ''
    modelSettingsRevision += 1
    const mutationId = (modelSettingMutationIds.get(settingId) ?? 0) + 1
    modelSettingMutationIds.set(settingId, mutationId)
    const validationErrors = validatePdfModelSetting(nextSetting)
    setModelSettingErrors(settingId, validationErrors)
    if (hasPdfModelSettingErrors(validationErrors)) {
      return
    }
    const previousSave = modelSettingSaveChains.get(settingId) ?? Promise.resolve()
    const nextSave = previousSave
      .catch(() => undefined)
      .then(async () => {
        try {
          const settings = await updatePdfModelSetting(settingId, {
            selectedProvider: nextSetting.selectedProvider,
            selectedModel: nextSetting.selectedModel,
          })
          if (modelSettingMutationIds.get(settingId) !== mutationId) {
            return
          }
          const savedSetting = settings.find((setting) => setting.id === settingId)
          if (savedSetting) {
            replaceModelSetting(savedSetting)
            setModelSettingErrors(settingId, {})
          }
        } catch (error: unknown) {
          if (modelSettingMutationIds.get(settingId) !== mutationId) {
            return
          }
          setModelSettingErrors(settingId, {
            selectedModel: toErrorMessage(error),
          })
        }
      })
    modelSettingSaveChains.set(settingId, nextSave)
    await nextSave
  }

  function setActiveTab(tab: PdfManagementInsightTab): void {
    activeTab.value = tab
  }

  function invalidateSummaryOperation(): void {
    summaryOperationId += 1
    summaryTaskPolling.stopPolling()
    summaryTasks.value = []
    isSummaryGenerating.value = false
  }

  async function refreshSummaryTarget(
    operationId: number,
    targetFileIds: string[],
  ): Promise<void> {
    if (operationId !== summaryOperationId || targetFileIds.length !== 1) {
      return
    }
    const fileId = targetFileIds[0]
    if (!fileId || selectedFile.value?.id !== fileId) {
      return
    }
    await loadDocumentDetail(fileId)
  }

  function replaceModelSetting(nextSetting: PdfModelSetting): void {
    modelSettings.value = modelSettings.value.map((setting) =>
      setting.id === nextSetting.id ? nextSetting : setting,
    )
  }

  function setModelSettingErrors(
    settingId: string,
    errors: PdfModelSettingFieldErrors,
  ): void {
    modelSettingErrors.value = {
      ...modelSettingErrors.value,
      [settingId]: errors,
    }
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
    modelSettingErrors,
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
