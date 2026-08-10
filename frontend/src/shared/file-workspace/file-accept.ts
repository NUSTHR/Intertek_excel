/**
 * Parses the value of an `<input type="file" accept="…">` attribute into
 * a list of accept clauses. Each clause is one of:
 * - `ext:.pdf` (extension)
 * - `mime:application/pdf` (MIME type)
 * - `glob:image/*` (wildcard subtype)
 */
export type AcceptClause =
  | { kind: 'extension'; value: string }
  | { kind: 'mime'; value: string }
  | { kind: 'glob'; subtype: string }

export function parseAccept(accept: string): AcceptClause[] {
  if (!accept) {
    return []
  }
  return accept
    .split(',')
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0)
    .map((entry) => {
      if (entry.startsWith('.')) {
        return { kind: 'extension', value: entry }
      }
      if (entry.endsWith('/*')) {
        return { kind: 'glob', subtype: entry.slice(0, -2) }
      }
      return { kind: 'mime', value: entry }
    })
}

export function matchesAccept(file: File, clauses: AcceptClause[]): boolean {
  if (clauses.length === 0) {
    return true
  }
  const name = file.name.toLowerCase()
  const type = file.type.toLowerCase()
  for (const clause of clauses) {
    if (clause.kind === 'extension') {
      if (name.endsWith(clause.value)) {
        return true
      }
    } else if (clause.kind === 'glob') {
      if (type.startsWith(`${clause.subtype}/`)) {
        return true
      }
    } else {
      if (type === clause.value) {
        return true
      }
    }
  }
  return false
}
