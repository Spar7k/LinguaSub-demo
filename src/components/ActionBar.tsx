type ActionBarProps = {
  previousLabel: string
  secondaryLabel: string
  primaryLabel: string
  note: string
  previousDisabled?: boolean
  secondaryDisabled?: boolean
  primaryDisabled?: boolean
  onPreviousClick?: () => void
  onSecondaryClick?: () => void
  onPrimaryClick?: () => void
}

export function ActionBar({
  previousLabel,
  secondaryLabel,
  primaryLabel,
  note,
  previousDisabled = false,
  secondaryDisabled = false,
  primaryDisabled = false,
  onPreviousClick,
  onSecondaryClick,
  onPrimaryClick,
}: ActionBarProps) {
  return (
    <footer className="action-bar">
      <div className="action-bar__surface">
        <p className="action-bar__note">{note}</p>

        <div className="action-bar__buttons">
          <button
            type="button"
            className="button"
            disabled={previousDisabled || !onPreviousClick}
            onClick={onPreviousClick}
          >
            {previousLabel}
          </button>
          <button
            type="button"
            className="button button--secondary"
            disabled={secondaryDisabled || !onSecondaryClick}
            onClick={onSecondaryClick}
          >
            {secondaryLabel}
          </button>
          <button
            type="button"
            className="button button--primary"
            disabled={primaryDisabled || !onPrimaryClick}
            onClick={onPrimaryClick}
          >
            {primaryLabel}
          </button>
        </div>
      </div>
    </footer>
  )
}
