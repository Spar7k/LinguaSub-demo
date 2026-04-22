import type { SubtitleSegment } from '../types/models'
import { useI18n } from '../i18n/useI18n'
import { formatTimelineMs } from '../utils/timeline'

type EditableSubtitleRowProps = {
  segment: SubtitleSegment
  isRetranslating: boolean
  errorMessage: string | null
  onSourceChange: (segmentId: string, value: string) => void
  onTranslationChange: (segmentId: string, value: string) => void
  onRetranslate: (segment: SubtitleSegment) => void
}

function formatTimeline(segment: SubtitleSegment): string {
  return `${formatTimelineMs(segment.start)} -> ${formatTimelineMs(segment.end)}`
}

export function EditableSubtitleRow({
  segment,
  isRetranslating,
  errorMessage,
  onSourceChange,
  onTranslationChange,
  onRetranslate,
}: EditableSubtitleRowProps) {
  const { m } = useI18n()

  return (
    <article className={`editor-row ${isRetranslating ? 'editor-row--loading' : ''}`.trim()}>
      <div className="editor-row__time">
        <strong>{segment.id}</strong>
        <span>{formatTimeline(segment)}</span>
        <button
          type="button"
          className="button button--secondary"
          onClick={() => onRetranslate(segment)}
          disabled={isRetranslating}
        >
          {isRetranslating ? m.common.buttons.retranslating : m.common.buttons.retranslate}
        </button>
      </div>

      <div className="editor-row__fields">
        <label className="field-block">
          <span className="field-label">{m.common.misc.sourceText}</span>
          <textarea
            className="textarea-input"
            value={segment.sourceText}
            onChange={(event) => onSourceChange(segment.id, event.target.value)}
            rows={3}
            disabled={isRetranslating}
          />
        </label>

        <label className="field-block">
          <span className="field-label">{m.common.misc.translatedText}</span>
          <textarea
            className="textarea-input"
            value={segment.translatedText}
            onChange={(event) => onTranslationChange(segment.id, event.target.value)}
            rows={3}
            disabled={isRetranslating}
          />
        </label>

        {errorMessage ? (
          <div className="error-banner editor-row__error" role="alert">
            <strong>{m.previewPage.retranslationFailed}</strong>
            <p>{errorMessage}</p>
          </div>
        ) : null}
      </div>
    </article>
  )
}
