export interface BaseFileInsightToolbarProps {
  showDownloadPreview: boolean
  showFullscreen: boolean
  canDownloadPreview: boolean
  isFullscreen: boolean
  isDownloading: boolean
  isTogglingFullscreen: boolean
  downloadLabel: string
  fullscreenLabel: string
}

export interface BaseFileInsightToolbarEmits {
  downloadPreview: []
  toggleFullscreen: []
}
