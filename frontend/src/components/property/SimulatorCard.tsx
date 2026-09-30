import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useSaveSimulationAsPlan, useSimulateSchedule } from "@/api/hooks/useLoans"
import { DateInput } from "@/components/DateInput"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate, todayIso } from "@/lib/dates"
import { formatGBP } from "@/lib/format"
import { cn } from "@/lib/utils"

export function SimulatorCard({
  accountId,
  allowanceWarnings,
}: {
  accountId: number
  allowanceWarnings: { period_label: string | null; year_start: string; allowed_gbp: number; planned_gbp: number }[]
}) {
  const [extraMonthly, setExtraMonthly] = useState<number | undefined>(undefined)
  const [lumpSums, setLumpSums] = useState<{ date: string; amount_gbp: number }[]>([])
  const [lumpDate, setLumpDate] = useState<string | undefined>(todayIso())
  const [lumpAmount, setLumpAmount] = useState<number | undefined>(undefined)
  const [effect, setEffect] = useState<"reduce_term" | "reduce_payment" | undefined>(undefined)

  const simulate = useSimulateSchedule()
  const savePlan = useSaveSimulationAsPlan()

  useEffect(() => {
    const timer = setTimeout(() => {
      if ((extraMonthly ?? 0) <= 0 && lumpSums.length === 0) return
      simulate.mutate({
        accountId,
        payload: { extra_monthly_gbp: extraMonthly ?? 0, lump_sums: lumpSums, overpayment_effect: effect },
      })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, 400)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountId, extraMonthly, JSON.stringify(lumpSums), effect])

  function addLumpSum() {
    if (!lumpDate || lumpAmount === undefined) return
    setLumpSums((s) => [...s, { date: lumpDate, amount_gbp: lumpAmount }])
    setLumpAmount(undefined)
  }

  async function saveAsPlan() {
    try {
      await savePlan.mutateAsync({
        accountId,
        payload: { extra_monthly_gbp: extraMonthly ?? 0, lump_sums: lumpSums, overpayment_effect: effect },
      })
      toast.success("Saved as a Regular Payment")
      setExtraMonthly(undefined)
      setLumpSums([])
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the Regular Payment"))
    }
  }

  const result = simulate.data

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-4">
        <p className="font-heading text-2xl font-medium tracking-[-0.01em] text-ink">Overpayment simulator</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>Extra per month</Label>
            <MoneyInput value={extraMonthly} onChange={setExtraMonthly} className="w-36" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Effect</Label>
            <div className="inline-flex items-center gap-1 rounded-lg border border-border p-1 text-xs">
              {(["reduce_term", "reduce_payment"] as const).map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setEffect(opt)}
                  className={cn(
                    "rounded-md px-2 py-1",
                    effect === opt ? "bg-muted text-ink" : "text-ink-2 hover:text-ink"
                  )}
                >
                  {opt === "reduce_term" ? "Reduce term" : "Reduce payment"}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <Label>Lump sums</Label>
          <div className="flex flex-wrap items-end gap-2">
            <DateInput value={lumpDate} onChange={setLumpDate} className="w-36" />
            <MoneyInput value={lumpAmount} onChange={setLumpAmount} className="w-32" />
            <Button type="button" size="sm" variant="outline" onClick={addLumpSum}>
              Add lump sum
            </Button>
          </div>
          {lumpSums.length > 0 && (
            <ul className="flex flex-col gap-1 text-xs text-ink-2">
              {lumpSums.map((ls, i) => (
                <li key={`${ls.date}-${i}`} className="flex items-center gap-2">
                  <span>{formatDate(ls.date)}</span>
                  <Money value={ls.amount_gbp} />
                  <button
                    type="button"
                    className="text-ink-muted hover:text-loss"
                    onClick={() => setLumpSums((s) => s.filter((_, idx) => idx !== i))}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {result && (
          <div className="grid grid-cols-2 gap-3 rounded-lg bg-muted/40 p-3 sm:grid-cols-4">
            <StatTile label="New mortgage-free date" value={result.payoff_date ? formatDate(result.payoff_date) : "—"} />
            <StatTile label="Months saved" value={result.months_saved} />
            <StatTile label="Interest saved" value={<Money value={result.interest_saved_gbp} />} />
            <div className="flex items-end">
              <Button size="sm" onClick={saveAsPlan} disabled={savePlan.isPending}>
                Save as Regular Payment
              </Button>
            </div>
          </div>
        )}

        {allowanceWarnings.length > 0 && (
          <div className="flex flex-col gap-1">
            {allowanceWarnings.map((w, i) => (
              <p key={i} className="flex items-center gap-1.5 text-xs text-warn">
                ⚠ {w.period_label ?? "Fixed period"}: overpayments of {formatGBP(w.planned_gbp)} exceed the{" "}
                {formatGBP(w.allowed_gbp)} allowance for the year starting {formatDate(w.year_start)}.
              </p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
