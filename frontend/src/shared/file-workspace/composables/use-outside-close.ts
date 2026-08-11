import { onBeforeUnmount, onMounted, type Ref } from 'vue'

export interface OutsideCloseOptions {
  isOpen: Ref<boolean>
  containerRef: Ref<HTMLElement | null>
  // Optional second ref for portals (the popover lives in a different DOM
  // subtree than the trigger).
  portalRef?: Ref<HTMLElement | null>
  onClose: () => void
  /**
   * If set, the listener ignores events whose target is inside any of
   * these elements. Useful when the trigger is a button that should
   * toggle the menu but not close it.
   */
  ignoreRefs?: Ref<HTMLElement | null>[]
  /**
   * Selector for elements that may legitimately receive clicks inside
   * the menu (e.g. action items). Clicks on these elements do NOT
   * close the menu — the menu closes via the `select` / `close` event
   * path.
   */
  internalSelector?: string
}

/**
 * Listens to global `pointerdown` and `keydown` to close the host element
 * when the user clicks outside of it or presses Escape. The composable
 * installs the listeners on `onMounted` and tears them down on
 * `onBeforeUnmount`. It re-evaluates whether to act based on the
 * `isOpen` ref so the listener can stay installed for the lifetime of
 * the component.
 */
export function useOutsideClose(options: OutsideCloseOptions): void {
  const { isOpen, containerRef, onClose } = options

  function isInside(target: EventTarget | null): boolean {
    if (!(target instanceof Node)) {
      return false
    }
    if (containerRef.value && containerRef.value.contains(target)) {
      return true
    }
    if (options.portalRef?.value && options.portalRef.value.contains(target)) {
      return true
    }
    if (options.ignoreRefs) {
      for (const ref of options.ignoreRefs) {
        if (ref.value && ref.value.contains(target)) {
          return true
        }
      }
    }
    if (options.internalSelector && target instanceof Element) {
      if (target.closest(options.internalSelector)) {
        return true
      }
    }
    return false
  }

  function handlePointerDown(event: PointerEvent): void {
    if (!isOpen.value) {
      return
    }
    if (isInside(event.target)) {
      return
    }
    onClose()
  }

  function handleKeyDown(event: KeyboardEvent): void {
    if (!isOpen.value) {
      return
    }
    if (event.key === 'Escape') {
      event.stopPropagation()
      onClose()
    }
  }

  onMounted(() => {
    document.addEventListener('pointerdown', handlePointerDown, true)
    document.addEventListener('keydown', handleKeyDown, true)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', handlePointerDown, true)
    document.removeEventListener('keydown', handleKeyDown, true)
  })
}
