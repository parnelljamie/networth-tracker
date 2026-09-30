import { AlertTriangle } from "lucide-react"
import { useDepositProtection } from "@/api/hooks/useInsights"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Money } from "@/components/Money"

/** docs/03-domain-logic.md §9 "Deposit protection": cash accounts grouped by provider per
 * person, flagged when a person's total at one provider exceeds
 * settings.deposit_protection_limit_gbp (FSCS £85k/£1m temp-high-balance in practice — the
 * limit itself is a Settings value, not hard-coded here). */
export function DepositProtectionCard() {
  const { data, isLoading } = useDepositProtection()
  const entries = data?.entries ?? []

  if (!isLoading && entries.length === 0) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Deposit protection</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-ink-muted">Loading…</p>}
        {!isLoading && (
          <div className="flex flex-col gap-2">
            {entries.map((e) => (
              <div
                key={`${e.provider}-${e.person_id}`}
                className="flex items-center justify-between gap-3 text-sm"
              >
                <span className="min-w-0 truncate text-ink-2">
                  {e.provider} · {e.person_name}
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {e.exceeded && (
                    <AlertTriangle
                      className="size-3.5 text-warn"
                      aria-hidden="true"
                    />
                  )}
                  <Money
                    value={e.total_gbp}
                    className={e.exceeded ? "text-warn font-medium" : "text-ink"}
                  />
                  {e.exceeded && (
                    <span className="text-xs text-warn">
                      over <Money value={e.limit_gbp} />
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
