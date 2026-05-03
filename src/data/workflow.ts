export type SidebarItemKey =
  | 'import'
  | 'videoSubtitle'
  | 'recognition'
  | 'translation'
  | 'preview'
  | 'aiWorkbench'
  | 'export'
  | 'settings'

export type SidebarItem = {
  key: SidebarItemKey
  label: string
  description: string
  active?: boolean
  disabled?: boolean
}

export type SidebarStatus = {
  label: string
  hint: string
  points: string[]
}

export type HeaderMetric = {
  label: string
  value: string
  hint: string
}

export const sidebarItemKeys: SidebarItemKey[] = [
  'import',
  'videoSubtitle',
  'recognition',
  'translation',
  'preview',
  'aiWorkbench',
  'export',
  'settings',
]
