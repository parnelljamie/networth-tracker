import { useState } from "react"
import { toast } from "sonner"
import {
  useCreateRatePeriod,
  useDeleteRatePeriod,
  useRatePeriods,
  useUpdateRatePeriod,
  type RatePeriodIn,
} from "@/api/hooks/useLoans"
import { DateInput } from "@/components/DateInput"
import { Money } from "@/components/Money"
import { PercentInput } from "@/components/PercentInput"
import { Pct } from "@/components/Pct"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate, todayIso } from "@/lib/dates"
import { cn } from "@/lib/utils"

const RATE_TYPES = ["fixed", "tracker", "variable", "svr"] as const

export function RatePeriodsCard({ accountId }: { accountId: number }) {
  const { data: periods } = useRatePeriods(accountId)
  const createPeriod = useCreateRatePeriod()
  const updatePeriod = useUpdateRatePeriod(accountId)
  const deletePeriod = useDeleteRatePeriod(accountId)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<{
    start_date: string
    end_date: string | undefined
    annual_rate: number | undefined
    rate_type: (typeof RATE_TYPES)[number]
    label: string
    payment_override_gbp: number | undefined
  }>({ start_date: todayIso(), end_date: undefined, annual_rate: undefined, rate_type: "fixed", label: "", payment_override_gbp: undefined })

  function resetForm() {
    setEditingId(null)
    setForm({ start_date: todayIso(), end_date: undefined, annual_rate: undefined, rate_type: "fixed", label: "", payment_override_gbp: undefined })
  }

  function edit(id: number) {
    const p = (periods ?? []).find((row) => row.id === id)
    if (!p) return
    setEditingId(id)
    setForm({
      start_date: p.start_date,
      end_date: p.end_date ?? undefined,
      annual_rate: p.annual_rate,
      rate_type: p.rate_type,
      label: p.label ?? "",
      payment_override_gbp: p.payment_override_gbp ?? undefined,
    })
  }

  async function save() {
    if (form.annual_rate === undefined) return
    const payload: RatePeriodIn = {
      start_date: form.start_date,
      end_date: form.end_date ?? null,
      annual_rate: form.annual_rate,
      rate_type: form.rate_type,
      label: form.label || null,
      payment_override_gbp: form.payment_override_gbp ?? null,
    }
    try {
      if (editingId !== null) {
        await updatePeriod.mutateAsync({ id: editingId, payload })
      } else {
        await createPeriod.mutateAsync({ accountId, payload })
      }
      resetForm()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the rate period"))
    }
  }

  const sorted = [...(periods ?? [])].sort((a, b) => a.start_date.localeCompare(b.start_date))
  const timelineStart = sorted[0]?.start_date
  const timelineEnd = sorted.reduce((latest, p) => (p.end_date && p.end_date > latest ? p.end_date : latest), sorted[sorted.length - 1]?.end_date ?? sorted[sorted.length - 1]?.start_date ?? "")

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-4">
        <p className="font-heading text-2xl font-medium tracking-[-0.01em] text-ink">Rate periods</p>

        {sorted.length > 0 && timelineStart && (
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
            {sorted.map((p) => {
              const start = new Date(timelineStart).getTime()
              const end = new Date(timelineEnd || p.end_date || p.start_date).getTime()
              const total = Math.max(end - start, 1)
              const segStart = new Date(p.start_date).getTime()
              const segEnd = new Date(p.end_date ?? timelineEnd ?? p.start_date).getTime()
              const width = Math.max(((segEnd - segStart) / total) * 100, 1)
              return (
                <div
                  key={p.id}
                  title={`${p.label ?? p.rate_type} — ${(p.annual_rate * 100).toFixed(2)}%`}
                  style={{ width: `${width}%`, backgroundColor: p.rate_type === "fixed" ? "var(--accent)" : "var(--ink-muted)" }}
                  className="h-full"
                />
              )
            })}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-ink-muted">
                <th className="py-1.5 font-normal">Start</th>
                <th className="py-1.5 font-normal">End</th>
                <th className="py-1.5 text-right font-normal">Rate</th>
                <th className="py-1.5 pl-4 font-normal">Type</th>
                <th className="py-1.5 font-normal">Label</th>
                <th className="py-1.5 text-right font-normal">Payment override</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sorted.map((p) => (
                <tr key={p.id} className="border-b border-border">
                  <td className="py-1.5">{formatDate(p.start_date)}</td>
                  <td className="py-1.5">{p.end_date ? formatDate(p.end_date) : "Open-ended"}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    <Pct value={p.annual_rate} decimals={2} />
                  </td>
                  <td className="py-1.5 pl-4 text-ink-2">{p.rate_type}</td>
                  <td className="py-1.5 text-ink-2">{p.label ?? "—"}</td>
                  <td className="py-1.5 text-right">
                    {p.payment_override_gbp ? <Money value={p.payment_override_gbp} /> : "—"}
                  </td>
                  <td className="py-1.5 text-right">
                    <button type="button" className="text-xs text-ink-muted hover:text-ink" onClick={() => edit(p.id)}>
                      Edit
                    </button>{" "}
                    <button
                      type="button"
                      className="text-xs text-ink-muted hover:text-loss"
                      onClick={() => deletePeriod.mutate(p.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-4 text-center text-ink-muted">
                    No rate periods yet — after these end, the fallback rate applies.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-border p-3">
          <div className="flex flex-col gap-1.5">
            <Label>Start</Label>
            <DateInput value={form.start_date} onChange={(v) => setForm((f) => ({ ...f, start_date: v ?? todayIso() }))} className="w-32" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>End</Label>
            <DateInput value={form.end_date} onChange={(v) => setForm((f) => ({ ...f, end_date: v }))} className="w-32" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Rate</Label>
            <PercentInput value={form.annual_rate} onChange={(v) => setForm((f) => ({ ...f, annual_rate: v }))} className="w-24" />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Type</Label>
            <div className="inline-flex items-center gap-1 rounded-lg border border-border p-1 text-xs">
              {RATE_TYPES.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, rate_type: t }))}
                  className={cn("rounded-md px-1.5 py-1", form.rate_type === t ? "bg-muted text-ink" : "text-ink-2 hover:text-ink")}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Label</Label>
            <Input value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} className="w-32" />
          </div>
          <Button type="button" size="sm" onClick={save} disabled={form.annual_rate === undefined}>
            {editingId !== null ? "Save" : "Add period"}
          </Button>
          {editingId !== null && (
            <Button type="button" size="sm" variant="ghost" onClick={resetForm}>
              Cancel
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
