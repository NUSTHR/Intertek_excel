import type { PdfManagementNavItem } from './types'

export const pdfManagementNavItems: PdfManagementNavItem[] = [
  { id: 'chat', label: 'Chat', icon: 'chat_bubble' },
  { id: 'knowledge', label: 'Knowledge Base', icon: 'auto_awesome', active: true },
  { id: 'diagnostics', label: 'Parse Diagnostics', icon: 'analytics' },
]
