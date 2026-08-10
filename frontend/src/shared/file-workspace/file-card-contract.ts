/**
 * Cross-domain file workspace contracts.
 *
 * This module is the single source of truth for the data shapes that flow
 * between the file management / PDF knowledge features and the shared
 * `BaseFile*` components. Domain layers MUST NOT redefine these shapes; they
 * adapt their own data into them at the composable boundary.
 */

export type FileDomain = 'excel' | 'pdf'

export type FileKind = 'file' | 'folder'

export type FileActionId =
  | 'pin'
  | 'unpin'
  | 'rename'
  | 'hide'
  | 'show'
  | 'delete'
  | 'open-folder'

/**
 * Icon names that may be displayed inside the shared file workspace
 * components. The set is intentionally narrow so that the icon-system module
 * is the only place that needs to learn about new glyphs.
 */
export type FileWorkspaceIconName =
  | 'description'
  | 'picture_as_pdf'
  | 'table_chart'
  | 'table_rows'
  | 'folder'
  | 'folder_open'
  | 'visibility'
  | 'visibility_off'
  | 'edit'
  | 'delete'
  | 'more_vert'
  | 'push_pin'
  | 'chevron_right'
  | 'chevron_left'
  | 'cloud_upload'
  | 'refresh'
  | 'notifications'
  | 'download'
  | 'fullscreen'
  | 'fullscreen_exit'
  | 'check'
  | 'close'
  | 'add'
  | 'search'
  | 'upload_file'
  | 'keyboard_arrow_down'
  | 'schema'
  | 'auto_awesome'
  | 'bolt'
  | 'tune'
  | 'account_tree'

/**
 * The unified file row view model consumed by `BaseFileRow.vue`. Both
 * Excel and PDF adapt their native file records into this shape.
 */
export interface BaseFileRowViewModel {
  id: string
  domain: FileDomain
  kind: FileKind
  displayName: string
  metaParts: string[]
  iconName: FileWorkspaceIconName
  isSelected: boolean
  isPinned: boolean
  isMultiSelectable: boolean
  isChecked: boolean
  isProgressing: boolean
  progressPercent: number
  isFolderOpenable: boolean
  visibilityChip?: string
  statusTone?: 'default' | 'progress' | 'success' | 'warning' | 'danger'
}

export interface BaseFileRowEmits {
  select: [vm: BaseFileRowViewModel]
  toggleCheck: [vm: BaseFileRowViewModel]
  openFolder: [vm: BaseFileRowViewModel]
  openMenu: [vm: BaseFileRowViewModel]
  requestAction: [vm: BaseFileRowViewModel, action: FileActionId]
}
