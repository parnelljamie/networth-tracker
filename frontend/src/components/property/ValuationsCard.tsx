import { useState } from "react"
import { toast } from "sonner"
import { useAccountBalances, useSaveBalance } from "@/api/hooks/useBalances"
import { DateInput } from "@/components/DateInput"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate, todayIso } from "@/lib/dates"

export function ValuationsCard({ propertyId, loanId }: { propertyId: number; loanId: number | undefined }) {
  const { data: propertyBalances } = useAccountBalances(propertyId)
  const { data: loanBalances } = useAccountBalances(loanId)
  const saveBalance = useSaveBalance()

  const [propDate, setPropDate] = useState<string | undefined>(todayIso())
  const [propAmount, setPropAmount] = useState<number | undefined>(undefined)
  const [statementDate, setStatementDate] = useState<string | undefined>(todayIso())
  const [statementAmount, setStatementAmount] = useState<number | undefined>(undefined)

  async function addValuation() {
    if (propAmount === undefined || !propDate) return
    try {
      await saveBalance.mutateAsync({ accountId: propertyId, payload: { date: propDate, balance_gbp: propAmount, source: "valuation" } })
      setPropAmount(undefined)
      toast.success("Valuation saved")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the valuation"))
    }
  }

  async function addStatement() {
    if (!loanId || statementAmount === undefined || !statementDate) return
    try {
      await saveBalance.mutateAsync({ accountId: loanId, payload: { date: statementDate, balance_gbp: statementAmount, source: "statement" } })
      setStatementAmount(undefined)
      toast.success("Statement balance saved")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the statement balance"))
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="flex flex-col gap-3 pt-4">
          <p className="font-heading text-2xl font-medium tracking-[-0.01em] text-ink">Property valuations</p>
          <div className="flex items-end gap-2">
            <DateInput value={propDate} onChange={setPropDate} className="w-36" />
            <MoneyInput value={propAmount} onChange={setPropAmount} className="w-32" />
            <Button size="sm" onClick={addValuation} disabled={propAmount === undefined}>
              Add
            </Button>
          </div>
          <div className="divide-y divide-border">
            {(propertyBalances ?? []).map((entry) => (
              <div key={entry.id} className="flex items-center justify-between py-1.5 text-sm">
                <span className="text-ink-2">{formatDate(entry.date)}</span>
                <Money value={entry.balance_gbp} />
              </div>
            ))}
            {(propertyBalances ?? []).length === 0 && <p className="py-3 text-sm text-ink-muted">No valuations yet.</p>}
          </div>
          <p className="text-xs text-ink-muted">The growth rate is applied from the latest valuation.</p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-3 pt-4">
          <p className="font-heading text-2xl font-medium tracking-[-0.01em] text-ink">Mortgage statement balances</p>
          {loanId ? (
            <>
              <div className="flex items-end gap-2">
                <DateInput value={statementDate} onChange={setStatementDate} className="w-36" />
                <MoneyInput value={statementAmount} onChange={setStatementAmount} className="w-32" />
                <Button size="sm" onClick={addStatement} disabled={statementAmount === undefined}>
                  Add
                </Button>
              </div>
              <div className="divide-y divide-border">
                {(loanBalances ?? []).map((entry) => (
                  <div key={entry.id} className="flex items-center justify-between py-1.5 text-sm">
                    <span className="text-ink-2">{formatDate(entry.date)}</span>
                    <Money value={entry.balance_gbp} />
                  </div>
                ))}
                {(loanBalances ?? []).length === 0 && <p className="py-3 text-sm text-ink-muted">No statements yet.</p>}
              </div>
            </>
          ) : (
            <p className="text-sm text-ink-muted">No mortgage linked yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
