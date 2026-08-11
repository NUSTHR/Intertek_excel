import { computed, onMounted, ref, watch, type Ref } from 'vue'

import {
  createPdfSummaryTasks,
  getPdfDocumentDetail,
  getPdfSummaryTask,
  listPdfModelSettings,
  listPdfSummaryTasks,
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

type PdfSummaryPhase = 'idle' | 'submitting' | 'polling' | 'refreshing'

export function usePdfDocumentInsight(
  selectedFile: Ref<PdfManagedFile | undefined>,
  selectedFiles: Readonly<Ref<PdfManagedFile[]>>,
  allFiles: Readonly<Ref<PdfManagedFile[]>>,
) {
  const summaryTaskPolling = usePdfTaskPolling()
  const activeTab = ref<PdfManagementInsightTab>('summary')
  const documentDetail = ref<PdfDocumentDetail | null>(null)
  const modelSettings = ref<PdfModelSetting[]>([])
  const isDetailLoading = ref<boolean>(false)
  const summaryPhase = ref<PdfSummaryPhase>('idle')
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
  const isSummaryGenerating = computed(() => summaryPhase.value !== 'idle')

  onMounted(() => {
    void loadModelSettings()
    void restoreSummaryTasks()
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

  watch(
    () => [
      selectedFiles.value.map((file) => file.id).sort().join('|'),
      allFiles.value.map((file) => file.id).sort().join('|'),
    ].join('::'),
    () => {
      void restoreSummaryTasks()
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
    if (isSummaryGenerating.value) {
      return
    }
    const operationId = ++summaryOperationId
    const targetFileIds = selected.map((file) => file.id)
    const force = shouldForceSummaryRegeneration(selected, summary.value)
    summaryPhase.value = 'submitting'
    errorMessage.value = ''
    summaryTasks.value = []
    summaryTaskPolling.stopPolling()
    try {
      const nextTasks = await createPdfSummaryTasks({
        fileIds: targetFileIds,
        includeDescendants: true,
        force,
      })
      if (operationId !== summaryOperationId) {
        return
      }
      summaryTasks.value = nextTasks
      startSummaryTaskPolling(nextTasks, operationId, targetFileIds)
    } catch (error: unknown) {
      if (operationId === summaryOperationId) {
        errorMessage.value = toErrorMessage(error)
        summaryTasks.value = []
        summaryPhase.value = 'idle'
      }
    }
  }

  async function restoreSummaryTasks(): Promise<void> {
    const operationId = ++summaryOperationId
    summaryTaskPolling.stopPolling()
    try {
      const listedTasks = await listPdfSummaryTasks()
      if (operationId !== summaryOperationId) {
        return
      }
      const selectedIds = summaryTargetFileIds(selectedFiles.value, allFiles.value)
      const activeTasks = listedTasks.filter(
        (task) => selectedIds.has(task.fileId) && isActiveSummaryTask(task),
      )
      summaryTasks.value = activeTasks
      if (activeTasks.length > 0) {
        startSummaryTaskPolling(
          summaryTasks.value,
          operationId,
          [...selectedIds],
        )
      } else {
        summaryPhase.value = 'idle'
      }
    } catch (error: unknown) {
      if (operationId === summaryOperationId) {
        errorMessage.value = toErrorMessage(error)
        summaryTasks.value = []
        summaryPhase.value = 'idle'
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
      void finalizeSummaryTasks(operationId, targetFileIds, tasks)
      return
    }
    summaryPhase.value = 'polling'
    const taskIds = tasks.map((task) => task.id)
    summaryTaskPolling.startPolling({
      load: () => Promise.all(taskIds.map(getPdfSummaryTask)),
      isTerminal: (nextTasks) => nextTasks.every(isTerminalSummaryTask),
      onUpdate: (nextTasks) => {
        if (operationId === summaryOperationId) {
          summaryTasks.value = nextTasks
        }
      },
      onTerminal: (nextTasks) => finalizeSummaryTasks(
        operationId,
        targetFileIds,
        nextTasks,
      ),
      onError: (error, isFinalAttempt) => {
        if (isFinalAttempt && operationId === summaryOperationId) {
          errorMessage.value = toErrorMessage(error)
          summaryTasks.value = []
          summaryPhase.value = 'idle'
        }
      },
    })
  }

  async function finalizeSummaryTasks(
    operationId: number,
    targetFileIds: string[],
    tasks: PdfSummaryTask[],
  ): Promise<void> {
    if (operationId !== summaryOperationId) {
      return
    }
    summaryTasks.value = tasks
    const unsuccessfulTask = tasks.find(isUnsuccessfulSummaryTask)
    if (unsuccessfulTask) {
      errorMessage.value = unsuccessfulTask.errorMessage
        || unsuccessfulTask.detail
        || 'PDF summary generation failed.'
      summaryTasks.value = []
      summaryPhase.value = 'idle'
      return
    }
    summaryPhase.value = 'refreshing'
    try {
      await refreshSummaryTarget(operationId, targetFileIds)
    } finally {
      if (operationId === summaryOperationId) {
        summaryTasks.value = []
        summaryPhase.value = 'idle'
      }
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

  async function refreshSummaryTarget(
    operationId: number,
    targetFileIds: string[],
  ): Promise<void> {
    if (operationId !== summaryOperationId || targetFileIds.length !== 1) {
      return
    }
    const fileId = targetFileIds[0]
    if (
      !fileId
      || selectedFile.value?.id !== fileId
      || selectedFile.value.kind === 'folder'
    ) {
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
    modelSettings,
    modelSettingErrors,
    isDetailLoading,
    isSummaryGenerating,
    errorMessage,
    setActiveTab,
    generateSummary,
    loadModelSettings,
    updateModelPreference,
  }
}

function isTerminalSummaryTask(task: PdfSummaryTask): boolean {
  return ['ready', 'failed', 'skipped', 'cancelled'].includes(task.status)
}

function isActiveSummaryTask(task: PdfSummaryTask): boolean {
  return task.status === 'queued' || task.status === 'running'
}

function isUnsuccessfulSummaryTask(task: PdfSummaryTask): boolean {
  if (task.status === 'failed' || task.status === 'cancelled') {
    return true
  }
  return task.status === 'skipped' && task.result.reason !== 'already_ready'
}

function shouldForceSummaryRegeneration(
  selected: PdfManagedFile[],
  summary: PdfDocumentDetail['summary'] | null,
): boolean {
  return selected.length === 1
    && selected[0].kind !== 'folder'
    && summary?.fileId === selected[0].id
    && summary.status === 'ready'
}

function summaryTargetFileIds(
  selected: PdfManagedFile[],
  allFiles: PdfManagedFile[],
): Set<string> {
  const selectedIds = new Set(selected.map((file) => file.id))
  const fileLookup = new Map(allFiles.map((file) => [file.id, file]))
  const targetIds = new Set(selectedIds)
  for (const file of allFiles) {
    let parentId = file.parentId
    const visited = new Set<string>()
    while (parentId && !visited.has(parentId)) {
      if (selectedIds.has(parentId)) {
        targetIds.add(file.id)
        break
      }
      visited.add(parentId)
      parentId = fileLookup.get(parentId)?.parentId
    }
  }
  return targetIds
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF insight operation failed.'
}
