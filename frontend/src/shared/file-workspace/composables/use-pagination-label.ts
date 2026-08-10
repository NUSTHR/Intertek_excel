import { computed, type ComputedRef, type Ref } from 'vue'

import {
  FILE_WORKSPACE_PAGE_SIZE,
  type BaseFilePaginationItem,
  type BaseFilePaginationViewModel,
} from '../file-pagination-contract.ts'

/**
 * Build the unified pagination view model from the file library state.
 * The range label is mandatory in the cross-domain contract (Excel side
 * already produces it; this also brings parity to the PDF side).
 */
export function usePaginationLabel(options: {
  totalCount: Ref<number> | ComputedRef<number>
  currentPage: Ref<number>
}): ComputedRef<BaseFilePaginationViewModel> {
  const { totalCount, currentPage } = options

  return computed<BaseFilePaginationViewModel>(() => buildFilePaginationViewModel({
    totalCount: totalCount.value,
    currentPage: currentPage.value,
  }))
}

/**
 * Pure pagination state builder shared by both domains and the test suite.
 * The internal page invariant remains one-based even for an empty result set,
 * while `hasItems` and `showNavigation` ensure that no synthetic page is
 * presented to the user.
 */
export function buildFilePaginationViewModel(options: {
  totalCount: number
  currentPage: number
}): BaseFilePaginationViewModel {
  const total = normalizeTotalCount(options.totalCount)
  const pageCount = Math.max(1, Math.ceil(total / FILE_WORKSPACE_PAGE_SIZE))
  const safePage = clampPage(options.currentPage, pageCount)
  const hasItems = total > 0
  const start = hasItems ? (safePage - 1) * FILE_WORKSPACE_PAGE_SIZE + 1 : 0
  const end = hasItems ? Math.min(total, safePage * FILE_WORKSPACE_PAGE_SIZE) : 0

  return {
    currentPage: safePage,
    pageCount,
    totalCount: total,
    items: hasItems ? computePaginationItems(safePage, pageCount) : [],
    paginationLabel: hasItems ? `${start}-${end} of ${total}` : '0 of 0',
    pageSize: FILE_WORKSPACE_PAGE_SIZE,
    hasItems,
    canGoPrevious: hasItems && safePage > 1,
    canGoNext: hasItems && safePage < pageCount,
    showNavigation: hasItems && pageCount > 1,
  }
}

export function clampPage(page: number, pageCount: number): number {
  if (!Number.isFinite(page) || pageCount <= 0) {
    return 1
  }
  if (page < 1) {
    return 1
  }
  if (page > pageCount) {
    return pageCount
  }
  return Math.trunc(page)
}

function computePaginationItems(
  currentPage: number,
  pageCount: number,
): BaseFilePaginationItem[] {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, index) => pageItem(index + 1, currentPage))
  }
  const items: BaseFilePaginationItem[] = []
  const first = 1
  const last = pageCount
  const start = Math.max(2, currentPage - 1)
  const end = Math.min(pageCount - 1, currentPage + 1)
  items.push(pageItem(first, currentPage))
  if (start > 2) {
    items.push({ kind: 'ellipsis', key: 'leading' })
  }
  for (let page = start; page <= end; page += 1) {
    items.push(pageItem(page, currentPage))
  }
  if (end < pageCount - 1) {
    items.push({ kind: 'ellipsis', key: 'trailing' })
  }
  items.push(pageItem(last, currentPage))
  return items
}

function pageItem(page: number, currentPage: number): BaseFilePaginationItem {
  return {
    kind: 'page',
    page,
    isCurrent: page === currentPage,
  }
}

function normalizeTotalCount(totalCount: number): number {
  if (!Number.isFinite(totalCount) || totalCount <= 0) {
    return 0
  }
  return Math.trunc(totalCount)
}
