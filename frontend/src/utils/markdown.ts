interface ListState {
  type: 'ol' | 'ul'
}

interface TableRow {
  cells: string[]
}

export function renderMarkdown(markdown: string): string {
  const normalizedMarkdown = markdown.replace(/\r\n?/g, '\n').trim()
  if (!normalizedMarkdown) {
    return ''
  }

  const lines = normalizedMarkdown.split('\n')
  const html: string[] = []
  const listStack: ListState[] = []
  let paragraphLines: string[] = []
  let quoteLines: string[] = []
  let tableRows: TableRow[] = []
  let codeLines: string[] = []
  let codeLanguage = ''
  let isInCodeBlock = false

  const closeParagraph = (): void => {
    if (paragraphLines.length === 0) {
      return
    }
    html.push(`<p>${renderInline(paragraphLines.join(' '))}</p>`)
    paragraphLines = []
  }

  const closeQuotes = (): void => {
    if (quoteLines.length === 0) {
      return
    }
    html.push(`<blockquote>${renderMarkdown(quoteLines.join('\n'))}</blockquote>`)
    quoteLines = []
  }

  const closeTable = (): void => {
    if (tableRows.length === 0) {
      return
    }
    const [headerRow, ...bodyRows] = tableRows
    html.push(
      '<table>',
      '<thead>',
      `<tr>${headerRow.cells.map((cell) => `<th>${renderInline(cell)}</th>`).join('')}</tr>`,
      '</thead>',
    )
    if (bodyRows.length > 0) {
      html.push('<tbody>')
      for (const row of bodyRows) {
        html.push(`<tr>${row.cells.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`)
      }
      html.push('</tbody>')
    }
    html.push('</table>')
    tableRows = []
  }

  const closeListsTo = (targetDepth: number): void => {
    while (listStack.length > targetDepth) {
      html.push(`</${listStack.pop()?.type ?? 'ul'}>`)
    }
  }

  const closeOpenBlocks = (): void => {
    closeParagraph()
    closeQuotes()
    closeTable()
    closeListsTo(0)
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? ''
    const trimmed = line.trim()

    if (isInCodeBlock) {
      if (trimmed.startsWith('```')) {
        const languageClass = codeLanguage ? ` class="language-${escapeAttribute(codeLanguage)}"` : ''
        html.push(`<pre><code${languageClass}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
        codeLines = []
        codeLanguage = ''
        isInCodeBlock = false
      } else {
        codeLines.push(line)
      }
      continue
    }

    if (trimmed.startsWith('```')) {
      closeOpenBlocks()
      isInCodeBlock = true
      codeLanguage = trimmed.slice(3).trim().split(/\s+/)[0] ?? ''
      continue
    }

    if (!trimmed) {
      closeOpenBlocks()
      continue
    }

    const tableCells = parseTableCells(trimmed)
    const nextLine = lines[index + 1]?.trim() ?? ''
    if (tableRows.length > 0 && tableCells) {
      closeParagraph()
      closeQuotes()
      closeListsTo(0)
      tableRows.push({ cells: tableCells })
      continue
    }
    if (tableCells && isTableSeparator(nextLine)) {
      closeOpenBlocks()
      tableRows.push({ cells: tableCells })
      index += 1
      continue
    }

    closeTable()

    const headingMatch = /^(#{1,6})\s+(.+)$/.exec(trimmed)
    if (headingMatch) {
      closeParagraph()
      closeQuotes()
      closeListsTo(0)
      const level = headingMatch[1]?.length ?? 2
      html.push(`<h${level}>${renderInline(headingMatch[2] ?? '')}</h${level}>`)
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      closeOpenBlocks()
      html.push('<hr>')
      continue
    }

    if (trimmed.startsWith('>')) {
      closeParagraph()
      closeListsTo(0)
      quoteLines.push(trimmed.replace(/^>\s?/, ''))
      continue
    }

    closeQuotes()

    const unorderedListMatch = /^(\s*)[-*+]\s+(.+)$/.exec(line)
    const orderedListMatch = /^(\s*)\d+[.)]\s+(.+)$/.exec(line)
    const listMatch = unorderedListMatch ?? orderedListMatch
    if (listMatch) {
      closeParagraph()
      const listType = orderedListMatch ? 'ol' : 'ul'
      const depth = Math.min(Math.floor((listMatch[1]?.length ?? 0) / 2), 4)
      closeListsTo(depth)
      if (listStack[depth]?.type !== listType) {
        closeListsTo(depth)
        html.push(`<${listType}>`)
        listStack.push({ type: listType })
      }
      html.push(`<li>${renderInline(listMatch[2] ?? '')}</li>`)
      continue
    }

    closeListsTo(0)
    paragraphLines.push(trimmed)
  }

  if (isInCodeBlock) {
    const languageClass = codeLanguage ? ` class="language-${escapeAttribute(codeLanguage)}"` : ''
    html.push(`<pre><code${languageClass}>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
  }

  closeOpenBlocks()
  return html.join('')
}

function parseTableCells(line: string): string[] | null {
  if (!line.includes('|')) {
    return null
  }
  const trimmedLine = line.replace(/^\|/, '').replace(/\|$/, '')
  const cells = trimmedLine.split('|').map((cell) => cell.trim())
  return cells.length >= 2 ? cells : null
}

function isTableSeparator(line: string): boolean {
  const cells = parseTableCells(line)
  return Boolean(cells && cells.every((cell) => /^:?-{3,}:?$/.test(cell)))
}

function renderInline(value: string): string {
  let html = escapeHtml(value)
  const codeTokens: string[] = []
  html = html.replace(/`([^`]+)`/g, (_match, code: string) => {
    const token = `\u0000CODE${codeTokens.length}\u0000`
    codeTokens.push(`<code>${code}</code>`)
    return token
  })

  html = html.replace(/\[([^\]]+)]\((https?:\/\/[^\s)]+)\)/g, (_match, label: string, url: string) => {
    const safeUrl = escapeAttribute(url)
    return `<a href="${safeUrl}" target="_blank" rel="noreferrer">${label}</a>`
  })
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
  html = html.replace(/(?<!_)_([^_\n]+)_(?!_)/g, '<em>$1</em>')
  html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>')

  for (const [index, tokenHtml] of codeTokens.entries()) {
    html = html.replace(`\u0000CODE${index}\u0000`, tokenHtml)
  }

  return html
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function escapeAttribute(value: string): string {
  return escapeHtml(value).replace(/`/g, '&#96;')
}
