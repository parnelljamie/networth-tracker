import { useVirtualizer } from "@tanstack/react-virtual"
import { useEffect, useMemo, useRef, useState } from "react"
import { useSchedule, type ScheduleRowOut } from "@/api/hooks/useLoans"
import { Pct } from "@/components/Pct"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { formatDate } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { cn } from "@/lib/utils"
import { scheduleRowsToCsv } from "@/lib/property"

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function ScheduleCard({ accountId }: { accountId: number }) {
  const { data: schedule } = useSchedule(accountId)
  const [expandedYears, setExpandedYears] = useState<Set<number>>(new Set())
  const parentRef = useRef<HTMLDivElement>(null)

  const rows = useMemo(() => schedule?.rows ?? [], [schedule])
  const byYear = useMemo(() => {
    const map = new Map<number, ScheduleRowOut[]>()
    for (const row of rows) {
      const year = new Date(row.date).getFullYear()
      if (!map.has(year)) map.set(year, [])
      map.get(year)!.push(row)
    }
    return map
  }, [rows])

  const years = Array.from(byYear.keys()).sort((a, b) => a - b)

  useEffect(() => {
    if (years.length > 0 && expandedYears.size === 0) {
      setExpandedYears(new Set([years[0]]))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [years.length])

  type FlatRow = { kind: "year"; year: number; total: { payment: number; interest: number; principal: number; overpayment: number } } | { kind: "row"; row: ScheduleRowOut }

  const flat: FlatRow[] = []
  for (const year of years) {
    const yearRows = byYear.get(year)!
    const total = yearRows.reduce(
      (acc, r) => ({
        payment: acc.payment + r.payment,
        interest: acc.interest + r.interest,
        principal: acc.principal + r.principal,
        overpayment: acc.overpayment + r.overpayment,
      }),
      { payment: 0, interest: 0, principal: 0, overpayment: 0 }
    )
    flat.push({ kind: "year", year, total })
    if (expandedYears.has(year)) {
      for (const row of yearRows) flat.push({ kind: "row", row })
    }
  }

  const virtualizer = useVirtualizer({
    count: flat.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,
    overscan: 12,
  })

  function toggleYear(year: number) {
    setExpandedYears((s) => {
      const next = new Set(s)
      if (next.has(year)) next.delete(year)
      else next.add(year)
      return next
    })
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 pt-4">
        <div className="flex items-center justify-between">
          <p className="font-heading text-2xl font-medium tracking-[-0.01em] text-ink">Schedule</p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => downloadCsv(`schedule-${accountId}.csv`, scheduleRowsToCsv(rows))}
            disabled={rows.length === 0}
          >
            Export CSV
          </Button>
        </div>

        <div className="grid grid-cols-7 gap-2 border-b border-border pb-1.5 text-xs text-ink-muted">
          <span>Date</span>
          <span className="text-right">Rate</span>
          <span className="text-right">Payment</span>
          <span className="text-right">Interest</span>
          <span className="text-right">Principal</span>
          <span className="text-right">Overpayment</span>
          <span className="text-right">Closing balance</span>
        </div>

        <div ref={parentRef} style={{ height: 420, overflow: "auto" }}>
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const entry = flat[item.index]
              return (
                <div
                  key={item.key}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: item.size,
                    transform: `translateY(${item.start}px)`,
                  }}
                >
                  {entry.kind === "year" ? (
                    <button
                      type="button"
                      onClick={() => toggleYear(entry.year)}
                      className="grid w-full grid-cols-7 gap-2 bg-muted/60 px-1 py-1.5 text-left text-xs font-medium text-ink"
                    >
                      <span>{entry.year}</span>
                      <span />
                      <span className="text-right tabular-nums">{formatGBP(entry.total.payment)}</span>
                      <span className="text-right tabular-nums">{formatGBP(entry.total.interest)}</span>
                      <span className="text-right tabular-nums">{formatGBP(entry.total.principal)}</span>
                      <span className="text-right tabular-nums">{formatGBP(entry.total.overpayment)}</span>
                      <span />
                    </button>
                  ) : (
                    <div className="grid w-full grid-cols-7 gap-2 border-b border-border px-1 py-1.5 text-xs">
                      <span className="text-ink-2">{formatDate(entry.row.date)}</span>
                      <span className="text-right tabular-nums text-ink-2">
                        <Pct value={entry.row.annual_rate} decimals={2} />
                      </span>
                      <span className="text-right tabular-nums text-ink">{formatGBP(entry.row.payment)}</span>
                      <span className="text-right tabular-nums text-ink-2">{formatGBP(entry.row.interest)}</span>
                      <span className="text-right tabular-nums text-ink-2">{formatGBP(entry.row.principal)}</span>
                      <span className={cn("text-right tabular-nums", entry.row.overpayment > 0 ? "text-ink" : "text-ink-muted")}>
                        {entry.row.overpayment > 0 ? formatGBP(entry.row.overpayment) : "—"}
                      </span>
                      <span className="text-right tabular-nums text-ink">{formatGBP(entry.row.closing_balance)}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
        {rows.length === 0 && <p className="py-4 text-center text-sm text-ink-muted">No schedule yet.</p>}
      </CardContent>
    </Card>
  )
}
