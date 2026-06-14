export interface WorkspaceUploadConfig {
  max_bytes: number
  supported_extensions: string[]
}

export interface WorkspaceConfig {
  upload: WorkspaceUploadConfig
}
