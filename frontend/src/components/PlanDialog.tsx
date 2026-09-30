import { useState } from "react"
import { toast } from "sonner"
import type { RecurringPlanCreate, RecurringPlanOut } from "@/api/hooks/useRecurring"
import { useCreateRecurringPlan, useUpdateRecurringPlan } from "@/api/hooks/useRecurring"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { DateInput } from "@/components/DateInput"
import { MoneyInput } from "@/components/MoneyInput"
import { PercentInput } from "@/components/PercentInput"
import { apiErrorMessage } from "@/lib/api-error"
import { todayIso } from "@/lib/dates"

type Frequency = RecurringPlanCreate["frequency"]
type PlanKind = RecurringPlanCreate["kind"]
type ContributionSource = NonNullable<RecurringPlanCreate["contribution_source"]>

const FREQUENCY_LABELS: Record<Frequency, string> = {
  weekly: "Weekly",
  fortnightly: "Fortnightly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  annually: "Annually",
}

const SOURCE_LABELS: Record<ContributionSource, string> = {
  personal: "Personal",
  employer: "Employer",
  salary_sacrifice: "Salary sacrifice",
  tax_relief: "Tax relief",
  government_bonus: "Government bonus",
  transfer: "Transfer",
}

interface AllocationRow {
  instrumentId: number
  symbol: string
  weight: string
}

interface PlanDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  accountId: number
  isHoldings: boolean
  isLoan: boolean
  instruments: { id: number; symbol: string; name: string }[]
  plan?: RecurringPlanOut
  /** The account syncs from a broker (Trading 212), which records each payment when it lands. */
  brokerSynced?: boolean
}

export function PlanDialog({
  open,
  onOpenChange,
  accountId,
  isHoldings,
  isLoan,
  instruments,
  plan,
  brokerSynced = false,
}: PlanDialogProps) {
  const createPlan = useCreateRecurringPlan()
  const updatePlan = useUpdateRecurringPlan()

  const [name, setName] = useState(plan?.name ?? "")
  const [kind, setKind] = useState<PlanKind>(plan?.kind ?? (isLoan ? "overpayment" : "contribution"))
  const [amount, setAmount] = useState<number | undefined>(plan?.amount_gbp)
  const [frequency, setFrequency] = useState<Frequency>(plan?.frequency ?? "monthly")
  const [startDate, setStartDate] = useState<string | undefined>(plan?.start_date ?? todayIso())
  const [taxRelief, setTaxRelief] = useState<number | undefined>(plan?.tax_relief_rate ?? 0)
  const [source, setSource] = useState<ContributionSource>(plan?.contribution_source ?? "personal")
  const [autoRecord, setAutoRecord] = useState(plan?.auto_record ?? false)
  const [allocations, setAllocations] = useState<AllocationRow[]>(
    (plan?.allocations ?? []).map((a) => ({
      instrumentId: a.instrument_id,
      symbol: instruments.find((i) => i.id === a.instrument_id)?.symbol ?? String(a.instrument_id),
      weight: String(Math.round(a.weight * 100)),
    })) ?? []
  )

  const weightTotal = allocations.reduce((sum, a) => sum + (Number(a.weight) || 0), 0)
  const allocationsValid = allocations.length === 0 || Math.abs(weightTotal - 100) < 0.01

  function addAllocationRow() {
    const remaining = instruments.filter((i) => !allocations.some((a) => a.instrumentId === i.id))
    if (remaining.length === 0) return
    setAllocations([...allocations, { instrumentId: remaining[0].id, symbol: remaining[0].symbol, weight: "" }])
  }

  function updateAllocation(index: number, patch: Partial<AllocationRow>) {
    setAllocations(allocations.map((a, i) => (i === index ? { ...a, ...patch } : a)))
  }

  function removeAllocation(index: number) {
    setAllocations(allocations.filter((_, i) => i !== index))
  }

  const canSubmit =
    name.trim() !== "" && amount !== undefined && amount > 0 && startDate && allocationsValid

  async function submit() {
    if (!canSubmit || !startDate || amount === undefined) return
    const payload: RecurringPlanCreate = {
      account_id: accountId,
      name,
      kind,
      amount_gbp: amount,
      frequency,
      start_date: startDate,
      contribution_source: source,
      // Relief at source only applies to personal contributions; employer and salary sacrifice
      // money already goes in gross.
      tax_relief_rate: source === "personal" ? (taxRelief ?? 0) : 0,
      auto_record: brokerSynced ? false : autoRecord,
      allocations: allocations
        .filter((a) => Number(a.weight) > 0)
        .map((a) => ({ instrument_id: a.instrumentId, weight: Number(a.weight) / 100 })),
    }
    try {
      if (plan) {
        await updatePlan.mutateAsync({ id: plan.id, payload })
        toast.success("Regular Payment updated")
      } else {
        await createPlan.mutateAsync(payload)
        toast.success("Regular Payment added")
      }
      onOpenChange(false)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save that Regular Payment"))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{plan ? "Edit Regular Payment" : "Add Regular Payment"}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Monthly ISA" />
          </div>

          {!isLoan && (
            <div className="flex flex-col gap-1.5">
              <Label>Kind</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as PlanKind)}>
                <SelectTrigger className="w-full">
                  <SelectValue>{(v: string) => (v === "withdrawal" ? "Withdrawal" : "Contribution")}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contribution">Contribution</SelectItem>
                  <SelectItem value="withdrawal">Withdrawal</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Amount</Label>
              <MoneyInput value={amount} onChange={setAmount} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Frequency</Label>
              <Select value={frequency} onValueChange={(v) => setFrequency(v as Frequency)}>
                <SelectTrigger className="w-full">
                  <SelectValue>{(v: Frequency) => FREQUENCY_LABELS[v] ?? v}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(FREQUENCY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Start date</Label>
            <DateInput value={startDate} onChange={setStartDate} />
          </div>

          {!isLoan && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Source</Label>
                  <Select value={source} onValueChange={(v) => setSource(v as ContributionSource)}>
                    <SelectTrigger className="w-full">
                      <SelectValue>{(v: ContributionSource) => SOURCE_LABELS[v] ?? v}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(SOURCE_LABELS)
                        .filter(([value]) => value !== "tax_relief")
                        .map(([value, label]) => (
                          <SelectItem key={value} value={value}>
                            {label}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Tax relief</Label>
                  <PercentInput
                    value={source === "personal" ? taxRelief : 0}
                    onChange={setTaxRelief}
                    disabled={source !== "personal"}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <Label htmlFor="plan-auto-record">Auto-add at each payment date</Label>
                  <Switch
                    id="plan-auto-record"
                    checked={brokerSynced ? false : autoRecord}
                    onCheckedChange={setAutoRecord}
                    disabled={brokerSynced}
                  />
                </div>
                <p className="text-xs text-ink-muted">
                  {brokerSynced
                    ? "Off because this account syncs from Trading 212, which adds the real payment when it lands. It still counts in projections."
                    : "Off: the payment only counts in projections. On: it's also added to the account on each date."}
                </p>
              </div>
            </>
          )}

          {isHoldings && (
            <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <div className="flex items-center justify-between">
                <Label>Allocation</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addAllocationRow}
                  disabled={allocations.length >= instruments.length}
                >
                  <Plus />
                  Add instrument
                </Button>
              </div>
              {allocations.map((row, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Select
                    value={String(row.instrumentId)}
                    onValueChange={(v) => updateAllocation(i, { instrumentId: Number(v) })}
                  >
                    <SelectTrigger className="flex-1">
                      <SelectValue>
                        {(v: string) => instruments.find((instr) => String(instr.id) === v)?.symbol ?? v}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {instruments.map((instr) => (
                        <SelectItem key={instr.id} value={String(instr.id)}>
                          {instr.symbol}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    className="w-20 text-right"
                    value={row.weight}
                    onChange={(e) => updateAllocation(i, { weight: e.target.value })}
                    placeholder="%"
                  />
                  <button
                    type="button"
                    className="text-xs text-ink-muted hover:text-loss"
                    onClick={() => removeAllocation(i)}
                  >
                    Remove
                  </button>
                </div>
              ))}
              {allocations.length === 0 && (
                <p className="text-xs text-ink-muted">No allocation — contributions stay as cash.</p>
              )}
              {!allocationsValid && (
                <p className="text-xs text-loss">Weights must add up to 100% ({weightTotal.toFixed(0)}% so far).</p>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!canSubmit || createPlan.isPending || updatePlan.isPending}>
            {plan ? "Save" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
