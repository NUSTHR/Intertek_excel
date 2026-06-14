import type { WorkspaceConfig } from '../types/workspace-config'
import { defaultRequestOptions } from './config'
import { requestJson } from './errors'

export async function getWorkspaceConfig(): Promise<WorkspaceConfig> {
  return requestJson<WorkspaceConfig>(
    '/api/workspace/config',
    { method: 'GET' },
    defaultRequestOptions,
  )
}
