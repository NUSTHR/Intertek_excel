import { computed, ref } from 'vue'

import { getLlmModelOptions, getLlmPreference, saveLlmPreference } from '../../api/llm-api'
import { toErrorMessage } from '../workspace-utils'
import type { ModelStage } from '../workspace-types'
import type { LlmModelDefaults, LlmProviderOption } from '../../types/llm'
import type { ModelStageDraft } from '../../features/file-management'

interface LlmPreferenceOptions {
  onError?: (error: unknown) => void
}

export function useLlmPreferences(options: LlmPreferenceOptions = {}) {
  const availableLlmModels = ref<string[]>([])
  const availableLlmProviders = ref<LlmProviderOption[]>([])
  const summaryProvider = ref<string>('siliconflow')
  const summaryModel = ref<string>('')
  const routerProvider = ref<string>('siliconflow')
  const routerModel = ref<string>('')
  const answerProvider = ref<string>('siliconflow')
  const answerModel = ref<string>('')
  const draftSummaryProvider = ref<string>('siliconflow')
  const draftSummaryModel = ref<string>('')
  const draftRouterProvider = ref<string>('siliconflow')
  const draftRouterModel = ref<string>('')
  const draftAnswerProvider = ref<string>('siliconflow')
  const draftAnswerModel = ref<string>('')
  const isModelPreferenceSaving = ref<boolean>(false)
  const modelPreferenceFeedback = ref<string>('')
  const modelPreferenceFeedbackKind = ref<'success' | 'error'>('success')

  const modelStageDrafts = computed<ModelStageDraft[]>(() => [
    {
      stage: 'summary',
      label: 'Summary Model',
      provider: draftSummaryProvider.value,
      model: draftSummaryModel.value,
      modelOptions: modelsForProvider(draftSummaryProvider.value),
    },
    {
      stage: 'router',
      label: 'Router Model',
      provider: draftRouterProvider.value,
      model: draftRouterModel.value,
      modelOptions: modelsForProvider(draftRouterProvider.value),
    },
    {
      stage: 'answer',
      label: 'Chat Model',
      provider: draftAnswerProvider.value,
      model: draftAnswerModel.value,
      modelOptions: modelsForProvider(draftAnswerProvider.value),
    },
  ])

  const answerSupportsDeepThinking = computed(() => {
    const provider = availableLlmProviders.value.find(
      (item) => item.provider === answerProvider.value,
    )
    return provider?.deep_thinking_models.includes(answerModel.value) ?? false
  })

  const hasModelPreferenceDraftChanges = computed(() => {
    return (
      draftSummaryProvider.value !== summaryProvider.value ||
      draftSummaryModel.value !== summaryModel.value ||
      draftRouterProvider.value !== routerProvider.value ||
      draftRouterModel.value !== routerModel.value ||
      draftAnswerProvider.value !== answerProvider.value ||
      draftAnswerModel.value !== answerModel.value
    )
  })

  const canSaveModelPreference = computed(() => {
    return hasModelPreferenceDraftChanges.value && isCompleteModelPreference()
  })

  async function loadLlmModelOptions(): Promise<void> {
    const optionsResponse = await getLlmModelOptions()
    availableLlmModels.value = optionsResponse.models
    availableLlmProviders.value = optionsResponse.providers
    applyModelDefaults(optionsResponse.defaults)
    try {
      const preference = await getLlmPreference()
      applyModelDefaults(preference)
    } catch (error: unknown) {
      options.onError?.(error)
    }
  }

  function applyModelDefaults(defaults: LlmModelDefaults): void {
    summaryProvider.value = defaults.summary_provider
    summaryModel.value = defaults.summary_model
    routerProvider.value = defaults.router_provider
    routerModel.value = defaults.router_model
    answerProvider.value = defaults.answer_provider
    answerModel.value = defaults.answer_model
    ensureStageModel('summary')
    ensureStageModel('router')
    ensureStageModel('answer')
    resetModelPreferenceDraft()
  }

  function modelsForProvider(provider: string): string[] {
    return availableLlmProviders.value.find((item) => item.provider === provider)?.models ?? []
  }

  function ensureStageModel(stage: ModelStage): void {
    const provider =
      stage === 'summary'
        ? summaryProvider.value
        : stage === 'router'
          ? routerProvider.value
          : answerProvider.value
    const models = modelsForProvider(provider)
    if (stage === 'summary' && !models.includes(summaryModel.value)) {
      summaryModel.value = models[0] ?? ''
    }
    if (stage === 'router' && !models.includes(routerModel.value)) {
      routerModel.value = models[0] ?? ''
    }
    if (stage === 'answer' && !models.includes(answerModel.value)) {
      answerModel.value = models[0] ?? ''
    }
  }

  function ensureDraftStageModel(stage: ModelStage): void {
    const provider =
      stage === 'summary'
        ? draftSummaryProvider.value
        : stage === 'router'
          ? draftRouterProvider.value
          : draftAnswerProvider.value
    const models = modelsForProvider(provider)
    if (stage === 'summary' && !models.includes(draftSummaryModel.value)) {
      draftSummaryModel.value = models[0] ?? ''
    }
    if (stage === 'router' && !models.includes(draftRouterModel.value)) {
      draftRouterModel.value = models[0] ?? ''
    }
    if (stage === 'answer' && !models.includes(draftAnswerModel.value)) {
      draftAnswerModel.value = models[0] ?? ''
    }
  }

  function handleModelProviderChange(stage: ModelStage): void {
    ensureDraftStageModel(stage)
    modelPreferenceFeedback.value = ''
  }

  function handleModelDraftChange(): void {
    modelPreferenceFeedback.value = ''
  }

  function updateModelStageProvider(stage: ModelStage, provider: string): void {
    if (stage === 'summary') {
      draftSummaryProvider.value = provider
    } else if (stage === 'router') {
      draftRouterProvider.value = provider
    } else {
      draftAnswerProvider.value = provider
    }
    handleModelProviderChange(stage)
  }

  function updateModelStageModel(stage: ModelStage, model: string): void {
    if (stage === 'summary') {
      draftSummaryModel.value = model
    } else if (stage === 'router') {
      draftRouterModel.value = model
    } else {
      draftAnswerModel.value = model
    }
    handleModelDraftChange()
  }

  function resetModelPreferenceDraft(): void {
    draftSummaryProvider.value = summaryProvider.value
    draftSummaryModel.value = summaryModel.value
    draftRouterProvider.value = routerProvider.value
    draftRouterModel.value = routerModel.value
    draftAnswerProvider.value = answerProvider.value
    draftAnswerModel.value = answerModel.value
    modelPreferenceFeedback.value = ''
  }

  async function saveModelPreferenceDefaults(): Promise<void> {
    if (!isCompleteModelPreference()) {
      modelPreferenceFeedbackKind.value = 'error'
      modelPreferenceFeedback.value = 'Select a provider and model for every stage.'
      return
    }
    isModelPreferenceSaving.value = true
    modelPreferenceFeedback.value = ''
    try {
      const preference = await saveLlmPreference({
        summary_provider: draftSummaryProvider.value,
        summary_model: draftSummaryModel.value,
        router_provider: draftRouterProvider.value,
        router_model: draftRouterModel.value,
        answer_provider: draftAnswerProvider.value,
        answer_model: draftAnswerModel.value,
      })
      applyModelDefaults(preference)
      modelPreferenceFeedbackKind.value = 'success'
      modelPreferenceFeedback.value = 'Saved as workspace defaults.'
    } catch (error: unknown) {
      modelPreferenceFeedbackKind.value = 'error'
      modelPreferenceFeedback.value = toErrorMessage(error)
    } finally {
      isModelPreferenceSaving.value = false
    }
  }

  function isCompleteModelPreference(): boolean {
    return Boolean(
      draftSummaryProvider.value &&
        draftSummaryModel.value &&
        draftRouterProvider.value &&
        draftRouterModel.value &&
        draftAnswerProvider.value &&
        draftAnswerModel.value,
    )
  }

  return {
    availableLlmModels,
    availableLlmProviders,
    summaryProvider,
    summaryModel,
    routerProvider,
    routerModel,
    answerProvider,
    answerModel,
    draftSummaryProvider,
    draftSummaryModel,
    draftRouterProvider,
    draftRouterModel,
    draftAnswerProvider,
    draftAnswerModel,
    isModelPreferenceSaving,
    modelPreferenceFeedback,
    modelPreferenceFeedbackKind,
    modelStageDrafts,
    answerSupportsDeepThinking,
    hasModelPreferenceDraftChanges,
    canSaveModelPreference,
    loadLlmModelOptions,
    applyModelDefaults,
    modelsForProvider,
    updateModelStageProvider,
    updateModelStageModel,
    resetModelPreferenceDraft,
    saveModelPreferenceDefaults,
    isCompleteModelPreference,
  }
}
