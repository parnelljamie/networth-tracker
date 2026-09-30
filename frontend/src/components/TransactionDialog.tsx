import { useMemo, useState } from "react"
import { toast } from "sonner"
import type { TransactionCreate } from "@/api/hooks/useTransactions"
import { useCreateTransaction } from "@/api/hooks/useTransactions"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { DateInput } from "@/components/DateInput"
import { MoneyInput } from "@/components/MoneyInput"
import { apiErrorMessage } from "@/lib/api-error"
import { todayIso } from "@/lib/dates"

type TxnType = TransactionCreate["type"]

const NEEDS_INSTRUMENT: TxnType[] = ["BUY", "SELL"]
const TYPE_LABELS: Record<string, string> = {
  BUY: "Buy",
  SELL: "Sell",
  DEPOSIT: "Deposit",
  WITHDRAWAL: "Withdrawal",
  DIVIDEND: "Dividend",
  INTEREST: "Interest",
  FEE: "Fee",
  TAX: "Tax",
}
const NEGATIVE_TYPES = new Set(["WITHDRAWAL", "FEE", "TAX"])

interface Instrument {
  id: number
  symbol: string
  name: string
}

interface TransactionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  accountId: number
  instruments: Instrument[]
}

export function TransactionDialog({ open, onOpenChange, accountId, instruments }: TransactionDialogProps) {
  const createTransaction = useCreateTransaction()
  const [type, setType] = useState<TxnType>("BUY")
  const [date, setDate] = useState<string | undefined>(todayIso())
  const [instrumentId, setInstrumentId] = useState<number | undefined>(instruments[0]?.id)
  const [units, setUnits] = useState<number | undefined>(undefined)
  const [priceNative, setPriceNative] = useState<number | undefined>(undefined)
  const [fees, setFees] = useState<number | undefined>(0)
  const [plainAmount, setPlainAmount] = useState<number | undefined>(undefined)

  const needsInstrument = NEEDS_INSTRUMENT.includes(type)

  const computedAmount = useMemo(() => {
    if (!needsInstrument) return undefined
    if (units === undefined || priceNative === undefined) return undefined
    const gross = units * priceNative
    const feesValue = fees ?? 0
    return type === "BUY" ? -(gross + feesValue) : gross - feesValue
  }, [needsInstrument, units, priceNative, fees, type])

  function reset() {
    setType("BUY")
    setDate(todayIso())
    setUnits(undefined)
    setPriceNative(undefined)
    setFees(0)
    setPlainAmount(undefined)
  }

  async function submit() {
    if (!date) return
    const amount = needsInstrument ? computedAmount : plainAmount
    if (amount === undefined) return

    const payload: TransactionCreate = {
      date,
      type,
      instrument_id: needsInstrument ? instrumentId : undefined,
      units: needsInstrument ? units ?? 0 : 0,
      price_native: needsInstrument ? priceNative : undefined,
      fees_gbp: needsInstrument ? fees ?? 0 : 0,
      amount_gbp: needsInstrument ? amount : NEGATIVE_TYPES.has(type) ? -Math.abs(amount) : Math.abs(amount),
    }

    try {
      await createTransaction.mutateAsync({ accountId, payload })
      toast.success("Transaction added")
      reset()
      onOpenChange(false)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that transaction"))
    }
  }

  const canSubmit = date && (needsInstrument ? instrumentId && computedAmount !== undefined : plainAmount !== undefined)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add transaction</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label>Type</Label>
            <Select value={type} onValueChange={(v) => setType(v as TxnType)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Date</Label>
            <DateInput value={date} onChange={setDate} />
          </div>

          {needsInstrument && (
            <div className="flex flex-col gap-1.5">
              <Label>Instrument</Label>
              <Select
                value={instrumentId?.toString()}
                onValueChange={(v) => setInstrumentId(Number(v))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose an instrument" />
                </SelectTrigger>
                <SelectContent>
                  {instruments.map((i) => (
                    <SelectItem key={i.id} value={i.id.toString()}>
                      {i.symbol} — {i.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {needsInstrument ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Units</Label>
                  <MoneyInput value={units} onChange={setUnits} placeholder="0" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Price</Label>
                  <MoneyInput value={priceNative} onChange={setPriceNative} />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Fees</Label>
                <MoneyInput value={fees} onChange={setFees} />
              </div>
              {computedAmount !== undefined && (
                <p className="text-sm text-ink-muted">
                  Cash effect: <span className="font-mono-figures text-ink">£{computedAmount.toFixed(2)}</span>
                </p>
              )}
            </>
          ) : (
            <div className="flex flex-col gap-1.5">
              <Label>Amount</Label>
              <MoneyInput value={plainAmount} onChange={setPlainAmount} />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!canSubmit || createTransaction.isPending}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
