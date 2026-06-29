import type { PdfManagementNavItem } from './types'

export const pdfManagementNavItems: PdfManagementNavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: 'analytics' },
  { id: 'chat', label: 'Chat', icon: 'chat_bubble' },
  { id: 'files', label: 'Files', icon: 'folder_open', active: true },
  { id: 'knowledge', label: 'Knowledge Base', icon: 'auto_awesome' },
]
