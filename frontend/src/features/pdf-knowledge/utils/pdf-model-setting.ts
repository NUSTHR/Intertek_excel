import type {
  PdfModelSetting,
  PdfModelSettingFieldErrors,
} from '../types'

export function validatePdfModelSetting(
  setting: PdfModelSetting,
): PdfModelSettingFieldErrors {
  const supportedModels = setting.providerModels[setting.selectedProvider]
  if (!supportedModels) {
    return {
      selectedProvider: 'Select a supported provider.',
    }
  }
  if (!supportedModels.includes(setting.selectedModel)) {
    return {
      selectedModel: 'Select a model supported by this provider.',
    }
  }
  return {}
}

export function hasPdfModelSettingErrors(
  errors: PdfModelSettingFieldErrors,
): boolean {
  return Boolean(errors.selectedProvider || errors.selectedModel)
}
