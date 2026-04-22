import { useI18n } from '../i18n/useI18n'

type SubtitleSearchToolbarProps = {
  searchQuery: string
  visibleCount: number
  totalCount: number
  hasUnsavedChanges: boolean
  lastSavedAt: string | null
  onSearchChange: (value: string) => void
  onSaveChanges: () => void
}

export function SubtitleSearchToolbar({
  searchQuery,
  visibleCount,
  totalCount,
  hasUnsavedChanges,
  lastSavedAt,
  onSearchChange,
  onSaveChanges,
}: SubtitleSearchToolbarProps) {
  const { m } = useI18n()

  return (
    <div className="subtitle-toolbar">
      <div className="subtitle-toolbar__search">
        <label className="field-block" htmlFor="subtitle-search">
          <span className="field-label">{m.previewPage.searchLabel}</span>
          <input
            id="subtitle-search"
            className="text-input"
            type="search"
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={m.common.placeholders.searchSubtitle}
            spellCheck={false}
          />
        </label>
      </div>

      <div className="subtitle-toolbar__meta">
        <div className="toolbar-badge">
          <span className="toolbar-badge__label">{m.previewPage.showingLabel}</span>
          <strong>
            {visibleCount} / {totalCount}
          </strong>
        </div>
        <div className={`toolbar-badge ${hasUnsavedChanges ? 'toolbar-badge--warn' : ''}`.trim()}>
          <span className="toolbar-badge__label">{m.common.misc.editState}</span>
          <strong>{hasUnsavedChanges ? m.common.misc.unsavedChanges : m.common.misc.saved}</strong>
          <span className="toolbar-badge__hint">
            {lastSavedAt ? m.previewPage.lastSaved(lastSavedAt) : m.common.misc.noSaveRecordedYet}
          </span>
        </div>
        <button
          type="button"
          className="button button--primary"
          onClick={onSaveChanges}
          disabled={!hasUnsavedChanges}
        >
          {m.common.buttons.saveChanges}
        </button>
      </div>
    </div>
  )
}
