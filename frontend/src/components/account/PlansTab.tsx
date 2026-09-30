import { useState } from "react"
import { useHoldings } from "@/api/hooks/useHoldings"
import { type RecurringPlanOut, useDeleteRecurringPlan, useRecurringPlans } from "@/api/hooks/useRecurring"
import { PlanDialog } from "@/components/PlanDialog"
import { Money } from "@/components/Money"
import { Button } from "@/components/ui/button"
import { formatDate } from "@/lib/dates"

export function PlansTab({
  accountId,
  isHoldings,
  isLoan,
  brokerSynced = false,
}: {
  accountId: number
  isHoldings: boolean
  isLoan: boolean
  brokerSynced?: boolean
}) {
  const { data: plans } = useRecurringPlans({ accountId })
  const { data: holdings } = useHoldings(accountId)
  const deletePlan = useDeleteRecurringPlan()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingPlan, setEditingPlan] = useState<RecurringPlanOut | undefined>(undefined)
  // Bumped on every open so the dialog remounts and re-reads the plan it is editing.
  const [dialogKey, setDialogKey] = useState(0)

  const instruments = (holdings?.positions ?? []).map((p) => ({
    id: p.instrument.id,
    symbol: p.instrument.symbol,
    name: p.instrument.name,
  }))

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <Button
          size="sm"
          onClick={() => {
            setEditingPlan(undefined)
            setDialogKey((k) => k + 1)
            setDialogOpen(true)
          }}
        >
          Add Regular Payment
        </Button>
      </div>
      <div className="divide-y divide-border">
        {(plans ?? []).map((plan) => (
          <div key={plan.id} className="flex items-center gap-3 py-2 text-sm">
            <div className="min-w-0 flex-1">
              <button
                type="button"
                className="text-ink hover:underline"
                onClick={() => {
                  setEditingPlan(plan)
                  setDialogKey((k) => k + 1)
                  setDialogOpen(true)
                }}
              >
                {plan.name}
              </button>
              <p className="text-xs text-ink-muted">
                {plan.frequency} · {plan.kind}
                {plan.next_date ? ` · next ${formatDate(plan.next_date)}` : ""}
                {brokerSynced ? " · added by Trading 212 sync" : plan.auto_record ? " · auto-add" : ""}
              </p>
            </div>
            <Money value={plan.amount_gbp} className="text-ink" />
            <button
              type="button"
              className="text-xs text-ink-muted hover:text-loss"
              onClick={() => deletePlan.mutate(plan.id)}
            >
              Delete
            </button>
          </div>
        ))}
        {(plans ?? []).length === 0 && (
          <p className="py-4 text-sm text-ink-muted">No Regular Payments for this account yet.</p>
        )}
      </div>

      <PlanDialog
        key={dialogKey}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        accountId={accountId}
        isHoldings={isHoldings}
        isLoan={isLoan}
        instruments={instruments}
        plan={editingPlan}
        brokerSynced={brokerSynced}
      />
    </div>
  )
}
