import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const excelWorkspaceSource = readFileSync(
  new URL('../src/app/ExcelWorkspaceApp.vue', import.meta.url),
  'utf8',
)
const workspaceFilesStyles = readFileSync(
  new URL('../src/styles/workspace-files.css', import.meta.url),
  'utf8',
)
const workspaceChatStyles = readFileSync(
  new URL('../src/styles/workspace-chat.css', import.meta.url),
  'utf8',
)
const excelChatSource = readFileSync(
  new URL('../src/components/ChatPanel.vue', import.meta.url),
  'utf8',
)
const excelChatStyles = readFileSync(
  new URL('../src/styles/chat-message.css', import.meta.url),
  'utf8',
)
const pdfChatSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfChatWorkspace.vue',
    import.meta.url,
  ),
  'utf8',
)
const pdfWorkspaceStyles = readFileSync(
  new URL('../src/styles/pdf-workspace-alignment.css', import.meta.url),
  'utf8',
)

test('Excel file workspace exposes a semantic shortcut to the existing chat view', () => {
  const fileViewStart = excelWorkspaceSource.indexOf(
    '<section v-if="activeView === \'files\'" class="file-page">',
  )
  const chatViewStart = excelWorkspaceSource.indexOf(
    '<section\n        v-show="activeView === \'chat\'"',
    fileViewStart,
  )
  const shortcutPosition = excelWorkspaceSource.indexOf(
    'aria-label="Open Excel chat"',
    fileViewStart,
  )

  assert.ok(fileViewStart >= 0)
  assert.ok(shortcutPosition > fileViewStart)
  assert.ok(shortcutPosition < chatViewStart)
  assert.ok(excelWorkspaceSource.includes('@click="setActiveView(\'chat\')"'))
  assert.match(workspaceFilesStyles, /\.file-chat-fab\s*\{[^}]*position:\s*fixed;/s)
  assert.doesNotMatch(workspaceChatStyles, /\.file-chat-fab\s*\{[^}]*display:\s*none;/s)
})

test('PDF answering state uses an accessible evidence-oriented thinking indicator', () => {
  assert.ok(pdfChatSource.includes('class="pdfkb-message-row assistant pdfkb-thinking-message"'))
  assert.ok(pdfChatSource.includes('role="status"'))
  assert.ok(pdfChatSource.includes('aria-live="polite"'))
  assert.ok(pdfChatSource.includes('aria-busy="true"'))
  assert.match(
    pdfChatSource,
    /pdfkb-thinking-title[\s\S]*?pdfkb-assistant-avatar[\s\S]*?<AppIcon name="auto_awesome" \/>/,
  )
  assert.equal(pdfChatSource.includes('pdfkb-thinking-agent-icon'), false)
  assert.ok(pdfChatSource.includes("'Checking PDF evidence. Verifying citations. Composing.'"))
  assert.ok(pdfChatSource.includes("'Comparing PDF evidence. Verifying citations. Composing.'"))
  assert.equal(pdfChatSource.includes('pdfkb-typing-bubble'), false)
  assert.match(pdfWorkspaceStyles, /@media \(prefers-reduced-motion:\s*reduce\)/)
})

test('Excel and PDF thinking states reuse their static answer avatars', () => {
  assert.match(
    excelChatSource,
    /thinking-title[\s\S]*?assistant-bot-icon[\s\S]*?<AppIcon name="analytics" \/>/,
  )
  assert.equal(excelChatSource.includes('thinking-agent-icon'), false)
  assert.equal(excelChatStyles.includes('thinking-agent-icon'), false)
  assert.equal(excelChatStyles.includes('thinking-agent-spin'), false)
  assert.match(
    pdfChatSource,
    /pdfkb-thinking-title[\s\S]*?pdfkb-assistant-avatar[\s\S]*?<AppIcon name="auto_awesome" \/>/,
  )
  assert.equal(pdfChatSource.includes('pdfkb-thinking-agent-icon'), false)
})
