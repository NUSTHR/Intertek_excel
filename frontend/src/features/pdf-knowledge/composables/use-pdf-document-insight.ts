import { computed, onMounted, ref, watch, type Ref } from 'vue'

import {
  generatePdfDocumentSummary,
  getPdfDocumentDetail,
  listPdfModelSettings,
  updatePdfModelSetting,
} from '../../../api/pdf-knowledge-api'
import type {
  PdfDocumentDetail,
  PdfManagementInsightTab,
  PdfManagedFile,
  PdfModelSetting,
} from '../types'

export function usePdfDocumentInsight(selectedFile: Ref<PdfManagedFile | undefined>) {
  const activeTab = ref<PdfManagementInsightTab>('summary')
  const documentDetail = ref<PdfDocumentDetail | null>(null)
  const modelSettings = ref<PdfModelSetting[]>([])
  const isDetailLoading = ref<boolean>(false)
  const isSummaryGenerating = ref<boolean>(false)
  const errorMessage = ref<string>('')
  let detailRequestId = 0

  const summary = computed(() => documentDetail.value?.summary ?? null)
  const previewBlocks = computed(() => documentDetail.value?.previewBlocks ?? [])
  const schema = computed(() => documentDetail.value?.schema ?? [])
  const contextTags = computed(() => documentDetail.value?.tags ?? [])

  onMounted(() => {
    void loadModelSettings()
  })

  watch(
    () => selectedFile.value?.id,
    (fileId) => {
      if (!fileId) {
        documentDetail.value = null
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
    const fileId = selectedFile.value?.id
    if (!fileId) {
      return
    }
    isSummaryGenerating.value = true
    errorMessage.value = ''
    try {
      const nextSummary = await generatePdfDocumentSummary(fileId)
      documentDetail.value = {
        ...(documentDetail.value ?? {
          fileId,
          previewBlocks: [],
          schema: [],
          tags: [],
        }),
        fileId,
        summary: nextSummary,
      }
    } catch (error: unknown) {
      errorMessage.value = toErrorMessage(error)
    } finally {
      isSummaryGenerating.value = false
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
    try {
      modelSettings.value = await updatePdfModelSetting(settingId, {
        selectedProvider: nextSetting.selectedProvider,
        selectedModel: nextSetting.selectedModel,
      })
    } catch (error: unknown) {
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
    modelSettings,
    isDetailLoading,
    isSummaryGenerating,
    errorMessage,
    setActiveTab,
    generateSummary,
    loadModelSettings,
    updateModelPreference,
  }
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'PDF insight operation failed.'
}
