import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const rootWorkspaceSource = readFileSync(
  new URL('../src/app/ExcelWorkspaceApp.vue', import.meta.url),
  'utf8',
)
const globalSidebarSource = readFileSync(
  new URL('../src/app/shell/GlobalWorkspaceSidebar.vue', import.meta.url),
  'utf8',
)
const workspaceSidebarStateSource = readFileSync(
  new URL('../src/app/composables/use-workspace-sidebar.ts', import.meta.url),
  'utf8',
)
const workspaceShellStyleSource = readFileSync(
  new URL('../src/styles/workspace-shell.css', import.meta.url),
  'utf8',
)
const workspaceNavigationSource = readFileSync(
  new URL('../src/components/WorkspaceNavigation.vue', import.meta.url),
  'utf8',
)
const workspaceConstantsSource = readFileSync(
  new URL('../src/app/workspace-constants.ts', import.meta.url),
  'utf8',
)
const appIconsSource = readFileSync(
  new URL('../src/components/app-icons.ts', import.meta.url),
  'utf8',
)
const fileLayoutSource = readFileSync(
  new URL('../src/components/file-workspace/FileWorkspaceLayout.vue', import.meta.url),
  'utf8',
)
const fileSourceLayoutSource = readFileSync(
  new URL(
    '../src/components/file-workspace/FileWorkspaceSourcePane.vue',
    import.meta.url,
  ),
  'utf8',
)
const fileInsightLayoutSource = readFileSync(
  new URL(
    '../src/components/file-workspace/FileWorkspaceInsightPane.vue',
    import.meta.url,
  ),
  'utf8',
)
const fileWorkspaceTemplateStyleSource = readFileSync(
  new URL('../src/styles/file-workspace-template.css', import.meta.url),
  'utf8',
)
const excelFileSourcePanelSource = readFileSync(
  new URL(
    '../src/features/file-management/components/FileSourcePanel.vue',
    import.meta.url,
  ),
  'utf8',
)
const excelFileInsightPanelSource = readFileSync(
  new URL(
    '../src/features/file-management/components/FileInsightPane.vue',
    import.meta.url,
  ),
  'utf8',
)
const pdfFileSourcePanelSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfManagementFilePane.vue',
    import.meta.url,
  ),
  'utf8',
)
const pdfFileInsightPanelSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfManagementInsightPane.vue',
    import.meta.url,
  ),
  'utf8',
)
const retiredFileLayoutStyleSources = [
  '../src/style.css',
  '../src/styles/workspace-files.css',
  '../src/styles/file-management.css',
  '../src/styles/pdf-knowledge.css',
  '../src/styles/pdf-workspace-alignment.css',
  '../src/styles/pdf-management-alignment.css',
  '../src/styles/pdf-shared-alignment.css',
  '../src/styles/workspace-shell.css',
].map((path) => readFileSync(new URL(path, import.meta.url), 'utf8'))
const pdfWorkspaceSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfKnowledgeWorkspace.vue',
    import.meta.url,
  ),
  'utf8',
)
const pdfManagementSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfKnowledgeManagementWorkspace.vue',
    import.meta.url,
  ),
  'utf8',
)
const pdfSidebarSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfKnowledgeSidebar.vue',
    import.meta.url,
  ),
  'utf8',
)

test('one global sidebar owns all workspace-level navigation', () => {
  assert.ok(rootWorkspaceSource.includes('<GlobalWorkspaceSidebar'))
  assert.ok(globalSidebarSource.includes('aria-label="Chat workspaces"'))
  assert.ok(globalSidebarSource.includes('aria-label="File workspaces"'))
  assert.equal(rootWorkspaceSource.includes('Excel chat destinations'), false)
  assert.equal(pdfSidebarSource.includes('PDF chat destinations'), false)
  assert.equal(pdfSidebarSource.includes('openManagement'), false)
  assert.equal(pdfSidebarSource.includes('openExcelChat'), false)
})

test('global sidebar exposes KnowledgeAI branding and an accessible collapsed mode', () => {
  assert.ok(globalSidebarSource.includes('<h1>KnowledgeAI</h1>'))
  assert.ok(globalSidebarSource.includes("emit('toggleCollapse')"))
  assert.ok(globalSidebarSource.includes("'Expand navigation sidebar'"))
  assert.ok(globalSidebarSource.includes("'Collapse navigation sidebar'"))
  assert.ok(rootWorkspaceSource.includes("'sidebar-collapsed': isGlobalSidebarCollapsed"))
  assert.ok(rootWorkspaceSource.includes(':collapsed="isGlobalSidebarCollapsed"'))
  assert.ok(rootWorkspaceSource.includes('@toggle-collapse="toggleGlobalSidebar"'))
  assert.ok(workspaceSidebarStateSource.includes('ref(true)'))
  assert.equal(workspaceSidebarStateSource.includes('localStorage'), false)
  assert.equal(workspaceSidebarStateSource.includes('matchMedia'), false)
  assert.ok(workspaceShellStyleSource.includes('--workspace-sidebar-width: 64px'))
  assert.ok(workspaceShellStyleSource.includes('background: #f1f5f9'))
  assert.ok(workspaceShellStyleSource.includes('@media (prefers-reduced-motion: reduce)'))
})

test('global sidebar keeps its icon rail isolated and stable across workspace modes', () => {
  assert.equal((globalSidebarSource.match(/variant="global"/g) ?? []).length, 2)
  assert.equal(globalSidebarSource.includes('class="nav-item'), false)
  assert.equal(globalSidebarSource.includes('class="nav-glyph'), false)
  assert.ok(workspaceNavigationSource.includes("'workspace-global-nav': variant === 'global'"))
  assert.ok(workspaceNavigationSource.includes("'workspace-global-nav__item': variant === 'global'"))
  assert.ok(workspaceShellStyleSource.includes('.workspace-global-nav__item,'))
  assert.ok(workspaceShellStyleSource.includes('transform: none'))
  assert.equal(
    workspaceShellStyleSource.includes('.workspace-global-sidebar .nav-item'),
    false,
  )
})

test('collapsed sidebar uses a centered edge control and a non-scrolling divided rail', () => {
  assert.ok(workspaceShellStyleSource.includes('top: 50%'))
  assert.ok(workspaceShellStyleSource.includes('right: -11px'))
  assert.ok(workspaceShellStyleSource.includes('transform: translateY(-50%)'))
  assert.ok(workspaceShellStyleSource.includes("+ .workspace-navigation-group::before"))
  assert.ok(workspaceShellStyleSource.includes('overflow: hidden'))
  assert.equal(workspaceShellStyleSource.includes('width 180ms ease'), false)
  assert.equal(workspaceShellStyleSource.includes('padding 180ms ease'), false)
})

test('sidebar toggle icon and Excel file icon use dedicated presentation contracts', () => {
  assert.ok(workspaceShellStyleSource.includes('--icon-size: 14px'))
  assert.ok(workspaceShellStyleSource.includes('.workspace-sidebar-toggle .app-icon'))
  assert.ok(workspaceConstantsSource.includes("icon: 'spreadsheet_file'"))
  assert.ok(appIconsSource.includes('spreadsheet_file:'))
})

test('Excel and PDF file pages share the same presentation-only layout', () => {
  assert.ok(rootWorkspaceSource.includes('<FileWorkspaceLayout'))
  assert.ok(pdfManagementSource.includes('<FileWorkspaceLayout'))
  assert.ok(rootWorkspaceSource.includes('domain="excel"'))
  assert.ok(pdfManagementSource.includes('domain="pdf"'))
  assert.ok(rootWorkspaceSource.includes('<template #source>'))
  assert.ok(rootWorkspaceSource.includes('<template #insight>'))
  assert.ok(pdfManagementSource.includes('<template #source>'))
  assert.ok(pdfManagementSource.includes('<template #insight>'))
  assert.ok(fileLayoutSource.includes('<slot name="actions"></slot>'))
  assert.ok(fileLayoutSource.includes('<slot name="source"></slot>'))
  assert.ok(fileLayoutSource.includes('<slot name="insight"></slot>'))
  assert.ok(fileLayoutSource.includes('file-workspace-source-pane'))
  assert.ok(fileLayoutSource.includes('file-workspace-insight-pane'))
  assert.ok(fileSourceLayoutSource.includes('grid-template-rows') === false)
  assert.ok(fileSourceLayoutSource.includes('<slot name="header"></slot>'))
  assert.ok(fileSourceLayoutSource.includes('<slot name="upload"></slot>'))
  assert.ok(fileSourceLayoutSource.includes('<slot name="status"></slot>'))
  assert.ok(fileSourceLayoutSource.includes('<slot name="list"></slot>'))
  assert.ok(fileSourceLayoutSource.includes('<slot name="pagination"></slot>'))
  assert.ok(fileInsightLayoutSource.includes('<slot name="tabs"></slot>'))
  assert.ok(fileInsightLayoutSource.includes('<slot name="actions"></slot>'))
  assert.ok(fileWorkspaceTemplateStyleSource.includes('minmax(360px, 0.82fr)'))
  assert.ok(fileWorkspaceTemplateStyleSource.includes('minmax(560px, 1.18fr)'))
  assert.ok(fileWorkspaceTemplateStyleSource.includes('minmax(0, 1fr) auto'))
  assert.equal(fileLayoutSource.includes('../api/'), false)
  assert.equal(fileLayoutSource.includes('MinerU'), false)
  assert.equal(rootWorkspaceSource.includes('class="file-management-shell"'), false)
  assert.equal(pdfManagementSource.includes('class="pdfmgmt-main"'), false)
})

test('file domains use the same source and insight pane structures', () => {
  assert.ok(excelFileSourcePanelSource.includes('<FileWorkspaceSourcePane domain="excel">'))
  assert.ok(pdfFileSourcePanelSource.includes('<FileWorkspaceSourcePane domain="pdf"'))
  assert.ok(excelFileInsightPanelSource.includes('<FileWorkspaceInsightPane domain="excel"'))
  assert.ok(pdfFileInsightPanelSource.includes('<FileWorkspaceInsightPane domain="pdf"'))
  assert.ok(excelFileSourcePanelSource.includes('<template #pagination>'))
  assert.ok(pdfFileSourcePanelSource.includes('<template #pagination>'))
  assert.ok(fileWorkspaceTemplateStyleSource.includes("'header'"))
  assert.ok(fileWorkspaceTemplateStyleSource.includes("'upload'"))
  assert.ok(fileWorkspaceTemplateStyleSource.includes("'status'"))
  assert.ok(fileWorkspaceTemplateStyleSource.includes("'list'"))
  assert.ok(fileWorkspaceTemplateStyleSource.includes("'pagination'"))
})

test('legacy styles no longer own file-workspace geometry', () => {
  for (const source of retiredFileLayoutStyleSources) {
    assert.equal(source.includes('.file-management-shell'), false)
    assert.equal(source.includes('.pdfmgmt-main'), false)
    assert.equal(source.includes('.pdfmgmt-file-pane'), false)
    assert.equal(source.includes('.pdfmgmt-file-scroll'), false)
  }
})

test('Excel and PDF file topbars expose the same compact actions', () => {
  assert.ok(pdfManagementSource.includes('aria-label="Refresh files"'))
  assert.ok(pdfManagementSource.includes('<AppIcon name="refresh" />'))
  assert.ok(pdfManagementSource.includes('aria-label="Notifications"'))
  assert.ok(pdfManagementSource.includes('<AppIcon name="notifications" />'))
  assert.ok(pdfManagementSource.includes('@click="library.loadLibrary"'))
  assert.ok(rootWorkspaceSource.includes('@notifications-requested="showNotificationsNotice"'))
  assert.equal(pdfManagementSource.includes('Upload Folder'), false)
  assert.equal(pdfManagementSource.includes('webkitdirectory'), false)
  assert.equal(pdfManagementSource.includes('workspace-file-primary-action'), false)
})

test('PDF chat and file workspaces stay mounted without navigation cancellation', () => {
  assert.ok(pdfWorkspaceSource.includes('v-show="mode === \'management\'"'))
  assert.ok(pdfWorkspaceSource.includes('v-show="mode === \'chat\'"'))
  assert.equal(pdfWorkspaceSource.includes('cancelActiveOperations()'), false)
  assert.ok(rootWorkspaceSource.includes('v-if="hasMountedPdfWorkspace"'))
  assert.ok(rootWorkspaceSource.includes('v-show="activeView === \'pdf-chat\' || activeView === \'pdf-files\'"'))
})
