import { useState } from "react"
import { toast } from "sonner"
import { useAccountBalances, useSaveBalance } from "@/api/hooks/useBalances"
import { Money } from "@/components/Money"
import { DateInput } from "@/components/DateInput"
import { MoneyInput } from "@/components/MoneyInput"
import { apiErrorMessage } from "@/lib/api-error"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { formatDate, todayIso } from "@/lib/dates"

export function BalancesTab({ accountId }: { accountId: number }) {
  const { data: balances } = useAccountBalances(accountId)
  const saveBalance = useSaveBalance()
  const [date, setDate] = useState<string | undefined>(todayIso())
  const [amount, setAmount] = useState<number | undefined>(undefined)

  async function add() {
    if (amount === undefined || !date) return
    try {
      await saveBalance.mutateAsync({ accountId, payload: { date, balance_gbp: amount } })
      toast.success("Balance saved")
      setAmount(undefined)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save balance"))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border p-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label>Date</Label>
          <DateInput value={date} onChange={setDate} className="w-40" />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label>Balance</Label>
          <MoneyInput value={amount} onChange={setAmount} className="w-36" />
        </div>
        <Button onClick={add} disabled={amount === undefined || saveBalance.isPending}>
          Add
        </Button>
      </div>

      <div className="divide-y divide-border">
        {(balances ?? []).map((entry) => (
          <div key={entry.id} className="flex items-center justify-between py-2 text-sm">
            <span className="text-ink-2">{formatDate(entry.date)}</span>
            <Money value={entry.balance_gbp} className="text-ink" />
          </div>
        ))}
        {(balances ?? []).length === 0 && (
          <p className="py-4 text-sm text-ink-muted">No balances recorded yet.</p>
        )}
      </div>
    </div>
  )
}
