import { useMemo } from "react"
import { useAttribution } from "@/api/hooks/useInsights"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Money } from "@/components/Money"
import { todayIso } from "@/lib/dates"

interface AttributionCardProps {
  personId?: number
}

function monthStartIso(): string {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10)
}

/** docs/BUILD_PLAN.md Phase 7: "This month: +£2,140 contributions, +£3,020 markets, +£610
 * mortgage paid" — a breakdown of the current month's net worth change, per
 * docs/03-domain-logic.md §9's decomposition (backend/app/services/attribution_service.py). */
export function AttributionCard({ personId }: AttributionCardProps) {
  const start = useMemo(() => monthStartIso(), [])
  const end = useMemo(() => todayIso(), [])
  const { data, isLoading } = useAttribution({ start, end, personId })

  const rows = data
    ? [
        { label: "Contributions", value: data.contributions_gbp },
        { label: "Markets", value: data.market_gbp },
        { label: "Mortgage paid", value: data.mortgage_paid_gbp },
        { label: "Revaluation", value: data.revaluation_gbp },
        { label: "Other", value: data.other_gbp },
      ].filter((r) => Math.abs(r.value) > 0.5)
    : []

  return (
    <Card>
      <CardHeader>
        <CardTitle>This month</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
        {!isLoading && data && rows.length === 0 && (
          <p className="text-sm text-ink-muted">No change recorded yet this month.</p>
        )}
        {!isLoading && data && rows.length > 0 && (
          <>
            <p className="text-sm text-ink-2">
              {rows.map((r, i) => (
                <span key={r.label}>
                  {i > 0 ? ", " : ""}
                  <Money
                    value={r.value}
                    className={r.value >= 0 ? "text-gain" : "text-loss"}
                  />{" "}
                  {r.label.toLowerCase()}
                </span>
              ))}
            </p>
            <p className="mt-2 text-xs text-ink-muted">
              Net worth change: <Money value={data.total_gbp} />
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
