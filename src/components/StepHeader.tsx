import type { HeaderMetric } from '../data/workflow'
import { useI18n } from '../i18n/useI18n'

type StepHeaderProps = {
  current: number
  total: number
  title: string
  description: string
  statusLabel: string
  statusTone: 'success' | 'warn' | 'idle' | 'error'
  statusHint: string
  metrics: HeaderMetric[]
}

export function StepHeader({
  current,
  total,
  title,
  description,
  statusLabel,
  statusTone,
  statusHint,
  metrics,
}: StepHeaderProps) {
  const { language, setLanguage, m } = useI18n()

  return (
    <header className="step-header">
      <div className="step-header__top">
        <div className="step-header__eyebrow">
          <strong>
            {m.stepHeader.step(current, total)}
          </strong>
          <span>{m.common.currentStage}</span>
        </div>

        <div className="step-header__controls">
          <div className="step-header__status">
            <span className={`status-pill status-pill--${statusTone}`}>{statusLabel}</span>
            <span className="step-header__eyebrow">{statusHint}</span>
          </div>

          <div className="language-switch" role="group" aria-label={m.common.language.label}>
            <span className="language-switch__label">{m.common.language.label}</span>
            <div className="language-switch__buttons">
              <button
                type="button"
                className={`language-switch__button ${language === 'zh' ? 'language-switch__button--active' : ''}`.trim()}
                onClick={() => setLanguage('zh')}
                aria-pressed={language === 'zh'}
              >
                {m.common.language.zh}
              </button>
              <button
                type="button"
                className={`language-switch__button ${language === 'en' ? 'language-switch__button--active' : ''}`.trim()}
                onClick={() => setLanguage('en')}
                aria-pressed={language === 'en'}
              >
                {m.common.language.en}
              </button>
            </div>
          </div>
        </div>
      </div>

      <h2>{title}</h2>
      <p>{description}</p>

      <div className="metric-grid">
        {metrics.map((metric) => (
          <article key={metric.label} className="metric-card">
            <span className="metric-card__label">{metric.label}</span>
            <div className="metric-card__value">{metric.value}</div>
            <p className="metric-card__hint">{metric.hint}</p>
          </article>
        ))}
      </div>
    </header>
  )
}
