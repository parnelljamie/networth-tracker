import { useEffect, useState } from "react"
import { toast } from "sonner"
import { useCreateInstrument } from "@/api/hooks/useInstruments"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MoneyInput } from "@/components/MoneyInput"
import { apiErrorMessage } from "@/lib/api-error"

interface ManualInstrumentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialQuery?: string
  onCreated: (instrument: { id: number; symbol: string; name: string }) => void
}

export function ManualInstrumentDialog({
  open,
  onOpenChange,
  initialQuery,
  onCreated,
}: ManualInstrumentDialogProps) {
  const createInstrument = useCreateInstrument()
  const [name, setName] = useState(initialQuery ?? "")
  const [price, setPrice] = useState<number | undefined>(undefined)

  useEffect(() => {
    if (open) setName(initialQuery ?? "")
  }, [open, initialQuery])

  async function submit() {
    if (!name.trim() || price === undefined) return
    const symbol = `MANUAL:${name.trim().toUpperCase().replace(/\s+/g, "_")}`
    try {
      const instrument = await createInstrument.mutateAsync({
        symbol,
        price_source: "manual",
        name: name.trim(),
        manual_price_gbp: price,
      })
      onCreated(instrument)
      onOpenChange(false)
      setPrice(undefined)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that instrument"))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add manual instrument</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="manual-name">Name</Label>
            <Input id="manual-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Current price</Label>
            <MoneyInput value={price} onChange={setPrice} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={submit} disabled={!name.trim() || price === undefined || createInstrument.isPending}>
            Add instrument
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
