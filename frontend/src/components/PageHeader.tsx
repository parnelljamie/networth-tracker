import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface PageHeaderProps {
  title: ReactNode
  /** Small uppercase kicker above the title, e.g. "Property & mortgage". */
  eyebrow?: ReactNode
  description?: ReactNode
  /** Right-hand side: actions, a scope switcher, a headline figure. */
  actions?: ReactNode
  /** Shown before the text block, e.g. a person's avatar. */
  leading?: ReactNode
  className?: string
}

/** docs/05-ui.md "Type": every page opens with a serif title, optionally a kicker and a line. */
export function PageHeader({ title, eyebrow, description, actions, leading, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}>
      <div className="flex min-w-0 items-center gap-5">
        {leading}
        <div className="flex min-w-0 flex-col gap-1">
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h1 className="page-title mt-1 text-4xl break-words md:text-5xl">{title}</h1>
          {description && <p className="mt-1.5 max-w-2xl text-[15px] text-ink-2">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3 md:justify-end">{actions}</div>}
    </header>
  )
}
