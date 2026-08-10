import assert from 'node:assert/strict'
import test from 'node:test'
import { computed, ref } from 'vue'

import { clampPage, usePaginationLabel } from '../src/shared/file-workspace/composables/use-pagination-label.ts'

test('clampPage keeps the page inside [1, pageCount]', () => {
  assert.equal(clampPage(0, 5), 1)
  assert.equal(clampPage(6, 5), 5)
  assert.equal(clampPage(3, 5), 3)
})

test('clampPage returns 1 for non-finite or zero pageCount', () => {
  assert.equal(clampPage(NaN, 5), 1)
  assert.equal(clampPage(2, 0), 1)
})

test('usePaginationLabel: zero items render the canonical label', () => {
  const totalCount = ref(0)
  const currentPage = ref(1)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '0 of 0')
  assert.equal(label.value.pageCount, 1)
  assert.equal(label.value.hasItems, false)
  assert.equal(label.value.showNavigation, false)
  assert.deepEqual(label.value.items, [])
})

test('usePaginationLabel: first page range starts at 1', () => {
  const totalCount = ref(24)
  const currentPage = ref(1)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '1-6 of 24')
  assert.equal(label.value.pageCount, 4)
})

test('usePaginationLabel: middle page range reflects the slice', () => {
  const totalCount = ref(24)
  const currentPage = ref(3)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '13-18 of 24')
})

test('usePaginationLabel: partial last page renders correct range', () => {
  const totalCount = ref(20)
  const currentPage = ref(4)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '19-20 of 20')
})

test('usePaginationLabel: out-of-range page is clamped to the last page', () => {
  const totalCount = ref(24)
  const currentPage = ref(99)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.currentPage, 4)
  assert.equal(label.value.paginationLabel, '19-24 of 24')
})

test('usePaginationLabel: pageSize is fixed at 6 in the contract', () => {
  const totalCount = ref(60)
  const currentPage = ref(1)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.pageSize, 6)
})

test('usePaginationLabel: visiblePages includes both ends and ellipses for large sets', () => {
  const totalCount = ref(100)
  const currentPage = ref(5)
  const label = usePaginationLabel({ totalCount, currentPage })
  const items = label.value.items
  const pages = items.filter((item) => item.kind === 'page').map((item) => item.page)
  assert.equal(pages[0], 1)
  assert.equal(pages[pages.length - 1], 17)
  assert.ok(items.some((item) => item.kind === 'ellipsis'))
})

test('usePaginationLabel: tracks upstream totalCount changes', () => {
  const totalCount = ref(6)
  const currentPage = ref(1)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '1-6 of 6')
  totalCount.value = 7
  assert.equal(label.value.pageCount, 2)
  assert.equal(label.value.paginationLabel, '1-6 of 7')
})

test('usePaginationLabel: accepts a computed for totalCount', () => {
  const source = ref(0)
  const totalCount = computed(() => source.value + 12)
  const currentPage = ref(1)
  const label = usePaginationLabel({ totalCount, currentPage })
  assert.equal(label.value.paginationLabel, '1-6 of 12')
  source.value = 12
  assert.equal(label.value.paginationLabel, '1-6 of 24')
  source.value = 100
  currentPage.value = 2
  assert.equal(label.value.paginationLabel, '7-12 of 112')
})
