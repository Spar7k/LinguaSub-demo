import type { SidebarItem, SidebarStatus } from '../data/workflow'
import { useI18n } from '../i18n/useI18n'

type SidebarProps = {
  items: SidebarItem[]
  status: SidebarStatus
  onSelectItem?: (key: SidebarItem['key']) => void
}

export function Sidebar({ items, status, onSelectItem }: SidebarProps) {
  const { m } = useI18n()

  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>{m.common.appName}</h1>
        <p>{m.sidebar.description}</p>
      </div>

      <nav className="sidebar-nav" aria-label={m.sidebar.ariaLabel}>
        {items.map((item, index) => (
          <button
            key={item.key}
            type="button"
            className={`sidebar-item ${item.active ? 'sidebar-item--active' : ''} ${
              item.disabled ? 'sidebar-item--disabled' : ''
            }`.trim()}
            aria-current={item.active ? 'step' : undefined}
            disabled={item.disabled}
            onClick={() => onSelectItem?.(item.key)}
          >
            <span className="sidebar-item__index">{String(index + 1).padStart(2, '0')}</span>
            <span>
              <span className="sidebar-item__label">{item.label}</span>
            </span>
          </button>
        ))}
      </nav>

      <section className="sidebar-status" aria-label="Task status">
        <span className="sidebar-status__label">{m.common.taskStatus}</span>
        <div className="sidebar-status__value">{status.label}</div>
        <p className="sidebar-status__hint">{status.hint}</p>
      </section>
    </aside>
  )
}
