import { useMemo, useState } from "react"
import { toast } from "sonner"
import { useBulkSaveBalances, useQuickUpdateRows } from "@/api/hooks/useBalances"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { StalenessBadge } from "@/components/StalenessBadge"
import { apiErrorMessage } from "@/lib/api-error"
import { CATEGORY_LABELS, type Category } from "@/lib/categories"
import { todayIso } from "@/lib/dates"

interface QuickUpdateSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function QuickUpdateSheet({ open, onOpenChange }: QuickUpdateSheetProps) {
  const { data: rows } = useQuickUpdateRows()
  const bulkSave = useBulkSaveBalances()
  const [values, setValues] = useState<Record<number, number | undefined>>({})

  const grouped = useMemo(() => {
    if (!rows) return []
    const byOwner = new Map<string, typeof rows>()
    for (const row of rows) {
      const key = row.owners.join(" & ") || "Household"
      const list = byOwner.get(key) ?? []
      list.push(row)
      byOwner.set(key, list)
    }
    return Array.from(byOwner.entries()).map(([owner, accounts]) => ({
      owner,
      byCategory: Array.from(
        accounts
          .reduce((map, row) => {
            const list = map.get(row.category) ?? []
            list.push(row)
            map.set(row.category, list)
            return map
          }, new Map<string, typeof rows>())
          .entries()
      ),
    }))
  }, [rows])

  const filledCount = Object.values(values).filter((v) => v !== undefined).length

  async function save() {
    const entries = Object.entries(values)
      .filter(([, v]) => v !== undefined)
      .map(([accountId, balance_gbp]) => ({
        account_id: Number(accountId),
        date: todayIso(),
        balance_gbp: balance_gbp as number,
      }))
    if (entries.length === 0) return
    try {
      await bulkSave.mutateAsync(entries)
      toast.success(`Saved ${entries.length} update${entries.length === 1 ? "" : "s"}`)
      setValues({})
      onOpenChange(false)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save updates"))
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
        <SheetHeader className="gap-1 border-b border-border px-5 pt-7 pb-5 md:px-8">
          <span className="eyebrow">The monthly check-in</span>
          <SheetTitle>Quick update</SheetTitle>
          <SheetDescription>Type today’s balances. Leave a row empty to skip it.</SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 md:px-8">
          {grouped.length === 0 && (
            <p className="py-8 text-center text-sm text-ink-muted">
              No balance or modelled accounts to update yet.
            </p>
          )}
          {grouped.map((group) => (
            <div key={group.owner} className="pt-5">
              <h3 className="border-b border-border pb-1.5 font-heading text-xl text-ink italic">{group.owner}</h3>
              {group.byCategory.map(([category, accounts]) => (
                <div key={category}>
                  <p className="pt-3 pb-1 text-xs text-ink-muted">
                    {CATEGORY_LABELS[category as Category] ?? category}
                  </p>
                  <div className="flex flex-col">
                    {accounts.map((row) => (
                      <div key={row.account_id} className="flex items-center gap-3 border-b border-rule-soft py-2.5">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-ink">{row.name}</p>
                          <div className="flex items-center gap-2 text-xs">
                            {row.last_balance_gbp !== null && (
                              <Money value={row.last_balance_gbp} className="text-ink-muted" />
                            )}
                            <StalenessBadge
                              staleness={row.staleness as "ok" | "warn" | "alert"}
                              daysSince={row.days_since}
                            />
                          </div>
                          {row.modelled_value_gbp !== null && (
                            <p className="text-xs text-ink-muted">
                              Modelled today: <Money value={row.modelled_value_gbp} />
                            </p>
                          )}
                        </div>
                        <MoneyInput
                          className="w-32"
                          aria-label={`New value for ${row.name}`}
                          value={values[row.account_id]}
                          onChange={(v) => setValues((prev) => ({ ...prev, [row.account_id]: v }))}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>

        <SheetFooter className="border-t border-border px-5 py-4 md:px-8">
          <Button size="lg" onClick={save} disabled={filledCount === 0 || bulkSave.isPending} className="w-full">
            Save {filledCount || ""} update{filledCount === 1 ? "" : "s"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
