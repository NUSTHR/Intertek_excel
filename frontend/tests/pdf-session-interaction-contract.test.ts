import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const componentSource = readFileSync(
  new URL(
    '../src/features/pdf-knowledge/components/PdfRecentChatList.vue',
    import.meta.url,
  ),
  'utf8',
)

test('keeps the PDF session title inside the real open button', () => {
  const openButtonStart = componentSource.indexOf('class="pdfkb-session-open"')
  const openButtonEnd = componentSource.indexOf('</button>', openButtonStart)
  const titlePosition = componentSource.indexOf(
    '<strong :title="chat.title">{{ chat.title }}</strong>',
    openButtonStart,
  )

  assert.ok(openButtonStart >= 0)
  assert.ok(titlePosition > openButtonStart)
  assert.ok(titlePosition < openButtonEnd)
  assert.equal(componentSource.includes('pdfkb-session-hitbox'), false)
})

test('does not globally disable session opening while another session loads', () => {
  assert.equal(
    componentSource.includes(':disabled="isSessionLoading || isBusy(chat)"'),
    false,
  )
  assert.ok(componentSource.includes(':disabled="isBusy(chat)"'))
})
