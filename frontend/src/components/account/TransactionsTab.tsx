import { useState } from "react"
import { useHoldings } from "@/api/hooks/useHoldings"
import { useDeleteTransaction, useTransactions } from "@/api/hooks/useTransactions"
import { Money } from "@/components/Money"
import { TransactionDialog } from "@/components/TransactionDialog"
import { Button } from "@/components/ui/button"
import { formatDate } from "@/lib/dates"

export function TransactionsTab({ accountId }: { accountId: number }) {
  const { data } = useTransactions(accountId)
  const { data: holdings } = useHoldings(accountId)
  const deleteTransaction = useDeleteTransaction()
  const [dialogOpen, setDialogOpen] = useState(false)

  const instruments = (holdings?.positions ?? []).map((p) => ({
    id: p.instrument.id,
    symbol: p.instrument.symbol,
    name: p.instrument.name,
  }))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setDialogOpen(true)}>
          Add transaction
        </Button>
      </div>
      <div className="divide-y divide-border">
        {(data?.items ?? []).map((txn) => (
          <div key={txn.id} className="flex items-center gap-3 py-2 text-sm">
            <span className="w-24 text-ink-2">{formatDate(txn.date)}</span>
            <span className="w-28 text-ink">{txn.type}</span>
            {txn.units > 0 && <span className="w-16 text-right tabular-nums text-ink-2">{txn.units}</span>}
            <Money value={txn.amount_gbp} className="flex-1 text-right text-ink" />
            {txn.status === "pending" && (
              <span className="rounded bg-warn/20 px-1.5 py-0.5 text-xs text-warn">pending</span>
            )}
            <button
              type="button"
              className="text-xs text-ink-muted hover:text-loss"
              onClick={() => deleteTransaction.mutate(txn.id)}
            >
              Delete
            </button>
          </div>
        ))}
        {(data?.items ?? []).length === 0 && (
          <p className="py-4 text-sm text-ink-muted">No transactions yet.</p>
        )}
      </div>

      <TransactionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        accountId={accountId}
        instruments={instruments}
      />
    </div>
  )
}
