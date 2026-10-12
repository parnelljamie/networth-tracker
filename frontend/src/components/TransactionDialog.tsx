import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useInstrumentPriceOn } from "@/api/hooks/useInstruments"
import type { TransactionCreate } from "@/api/hooks/useTransactions"
import { useCreateTransaction } from "@/api/hooks/useTransactions"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { DateInput } from "@/components/DateInput"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate, todayIso } from "@/lib/dates"
import { formatUnits } from "@/lib/format"

type TxnType = TransactionCreate["type"]
/** Buys and sells can be entered by unit count, or by the money paid/received when the provider
 *  only shows the cash amount (typical for workplace pensions). */
type EntryMode = "amount" | "units"

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
const UNITS_DP = 1e8

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

function instrumentLabel(i: Instrument): string {
  if (!i.name || i.name === i.symbol) return i.symbol
  return `${i.name} (${i.symbol})`
}

export function TransactionDialog({ open, onOpenChange, accountId, instruments }: TransactionDialogProps) {
  const createTransaction = useCreateTransaction()
  const [type, setType] = useState<TxnType>("BUY")
  const [date, setDate] = useState<string | undefined>(todayIso())
  const [chosenInstrumentId, setInstrumentId] = useState<number | undefined>(undefined)
  const [mode, setMode] = useState<EntryMode>("amount")
  const [units, setUnits] = useState<number | undefined>(undefined)
  const [tradeAmount, setTradeAmount] = useState<number | undefined>(undefined)
  const [typedPrice, setTypedPrice] = useState<number | undefined>(undefined)
  const [priceEdited, setPriceEdited] = useState(false)
  const [fees, setFees] = useState<number | undefined>(0)
  const [plainAmount, setPlainAmount] = useState<number | undefined>(undefined)

  const needsInstrument = NEEDS_INSTRUMENT.includes(type)

  // Holdings load after the dialog mounts, so fall back to the first instrument until one is chosen.
  const instrumentId = chosenInstrumentId ?? instruments[0]?.id

  // Suggest the stored price for the chosen fund and date until the person types their own.
  const { data: storedPrice } = useInstrumentPriceOn(needsInstrument ? instrumentId : undefined, date)
  const priceNative = priceEdited ? typedPrice : storedPrice?.close_gbp

  const effectiveUnits = useMemo(() => {
    if (!needsInstrument) return undefined
    if (mode === "units") return units
    if (tradeAmount === undefined || !priceNative || priceNative <= 0) return undefined
    const feesValue = fees ?? 0
    // Buy: the amount paid covers the units and the fee. Sell: the amount received is after the fee.
    const gross = type === "BUY" ? tradeAmount - feesValue : tradeAmount + feesValue
    if (gross <= 0) return undefined
    return Math.round((gross / priceNative) * UNITS_DP) / UNITS_DP
  }, [needsInstrument, mode, units, tradeAmount, priceNative, fees, type])

  const computedAmount = useMemo(() => {
    if (!needsInstrument) return undefined
    if (mode === "amount") {
      if (tradeAmount === undefined || effectiveUnits === undefined) return undefined
      return type === "BUY" ? -Math.abs(tradeAmount) : Math.abs(tradeAmount)
    }
    if (units === undefined || priceNative === undefined) return undefined
    const gross = units * priceNative
    const feesValue = fees ?? 0
    return type === "BUY" ? -(gross + feesValue) : gross - feesValue
  }, [needsInstrument, mode, tradeAmount, effectiveUnits, units, priceNative, fees, type])

  function reset() {
    setType("BUY")
    setDate(todayIso())
    setMode("amount")
    setUnits(undefined)
    setTradeAmount(undefined)
    setInstrumentId(undefined)
    setTypedPrice(undefined)
    setPriceEdited(false)
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
      units: needsInstrument ? effectiveUnits ?? 0 : 0,
      price_native: needsInstrument ? priceNative : undefined,
      fees_gbp: needsInstrument ? fees ?? 0 : 0,
      amount_gbp: needsInstrument
        ? Math.round(amount * 100) / 100
        : NEGATIVE_TYPES.has(type)
          ? -Math.abs(amount)
          : Math.abs(amount),
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

  const canSubmit =
    date &&
    (needsInstrument
      ? instrumentId && effectiveUnits !== undefined && effectiveUnits > 0 && computedAmount !== undefined
      : plainAmount !== undefined)

  const instrumentsById = new Map(instruments.map((i) => [i.id.toString(), i]))
  const amountLabel = type === "BUY" ? "Amount invested" : "Amount received"

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
                <SelectValue>{(v: string) => TYPE_LABELS[v] ?? v}</SelectValue>
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
                value={instrumentId?.toString() ?? null}
                onValueChange={(v) => {
                  setInstrumentId(Number(v))
                  setPriceEdited(false)
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose an instrument">
                    {(v: string | null) => {
                      const i = v ? instrumentsById.get(v) : undefined
                      return i ? instrumentLabel(i) : "Choose an instrument"
                    }}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {instruments.map((i) => (
                    <SelectItem key={i.id} value={i.id.toString()}>
                      {instrumentLabel(i)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {needsInstrument ? (
            <>
              <div className="flex flex-col gap-1.5">
                <Label>Enter by</Label>
                <div className="grid grid-cols-2 gap-2" role="group" aria-label="Enter by">
                  <Button
                    type="button"
                    size="sm"
                    variant={mode === "amount" ? "secondary" : "outline"}
                    aria-pressed={mode === "amount"}
                    onClick={() => setMode("amount")}
                  >
                    Amount (£)
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={mode === "units" ? "secondary" : "outline"}
                    aria-pressed={mode === "units"}
                    onClick={() => setMode("units")}
                  >
                    Units
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {mode === "amount" ? (
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="txn-amount">{amountLabel}</Label>
                    <MoneyInput id="txn-amount" value={tradeAmount} onChange={setTradeAmount} />
                  </div>
                ) : (
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="txn-units">Units</Label>
                    <Input
                      id="txn-units"
                      type="number"
                      step="any"
                      min="0"
                      inputMode="decimal"
                      className="tabular-nums"
                      placeholder="0"
                      value={units ?? ""}
                      onChange={(e) => setUnits(e.target.value === "" ? undefined : Number(e.target.value))}
                    />
                  </div>
                )}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="txn-price">Price per unit</Label>
                  <MoneyInput
                    id="txn-price"
                    value={priceNative}
                    onChange={(v) => {
                      setPriceEdited(true)
                      setTypedPrice(v)
                    }}
                  />
                </div>
              </div>
              {storedPrice && !priceEdited && (
                <p className="-mt-1 text-xs text-ink-muted">
                  Price filled in from the stored close on {formatDate(storedPrice.date)}. Use your provider's price
                  if you have it.
                </p>
              )}
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="txn-fees">Fees</Label>
                <MoneyInput id="txn-fees" value={fees} onChange={setFees} />
              </div>
              {computedAmount !== undefined && effectiveUnits !== undefined && (
                <div className="flex flex-col gap-0.5 text-sm text-ink-muted">
                  {mode === "amount" && (
                    <p>
                      Units: <span className="tabular-nums text-ink">{formatUnits(effectiveUnits)}</span>
                    </p>
                  )}
                  <p>
                    Cash effect: <Money value={computedAmount} className="text-ink" />
                  </p>
                </div>
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
