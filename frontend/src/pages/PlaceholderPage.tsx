interface PlaceholderPageProps {
  title: string
  note?: string
}

export function PlaceholderPage({ title, note }: PlaceholderPageProps) {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="page-title text-4xl md:text-5xl">{title}</h1>
      <p className="text-ink-muted text-sm">{note ?? "Built in a later phase."}</p>
    </div>
  )
}
