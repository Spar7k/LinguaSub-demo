import type { ReactNode } from 'react'

type SectionCardProps = {
  eyebrow: string
  title: string
  description: string
  className?: string
  children: ReactNode
}

export function SectionCard({
  eyebrow,
  title,
  description,
  className,
  children,
}: SectionCardProps) {
  return (
    <section className={`section-card ${className ?? ''}`.trim()}>
      <span className="section-card__eyebrow">{eyebrow}</span>
      <h2 className="section-card__title">{title}</h2>
      <p className="section-card__desc">{description}</p>
      <div className="section-card__body">{children}</div>
    </section>
  )
}
