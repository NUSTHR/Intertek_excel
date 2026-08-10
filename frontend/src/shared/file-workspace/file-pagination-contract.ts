/**
 * `pageSize` is locked to 6 by the cross-domain contract. Both Excel and
 * PDF must use this value; if a domain ever needs a different page size, the
 * variance must be raised in the design doc and the contract relaxed in a
 * dedicated milestone.
 */
export const FILE_WORKSPACE_PAGE_SIZE = 6 as const

export type BaseFilePaginationItem =
  | {
      kind: 'page'
      page: number
      isCurrent: boolean
    }
  | {
      kind: 'ellipsis'
      key: 'leading' | 'trailing'
    }

export interface BaseFilePaginationViewModel {
  currentPage: number
  pageCount: number
  totalCount: number
  items: BaseFilePaginationItem[]
  paginationLabel: string
  pageSize: typeof FILE_WORKSPACE_PAGE_SIZE
  hasItems: boolean
  canGoPrevious: boolean
  canGoNext: boolean
  showNavigation: boolean
}

export interface BaseFilePaginationEmits {
  setPage: [page: number]
  stepPage: [direction: -1 | 1]
}
