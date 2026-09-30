import { DateInput } from "@/components/DateInput"
import { MoneyInput } from "@/components/MoneyInput"
import { PercentInput } from "@/components/PercentInput"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { numberOrUndefined, TPS_PRESET, type DbPensionDraft } from "@/lib/dbPension"
import { cn } from "@/lib/utils"

interface DbPensionFieldsProps {
  value: DbPensionDraft
  onChange: (value: DbPensionDraft) => void
}

/** Scheme terms for a defined-benefit pension, with a TPS preset. Figures come from the latest
 *  annual benefit statement. */
export function DbPensionFields({ value, onChange }: DbPensionFieldsProps) {
  const set = (patch: Partial<DbPensionDraft>) => onChange({ ...value, ...patch })
  // Editing a scheme rule turns the preset into a custom scheme.
  const setRule = (patch: Partial<DbPensionDraft>) => set({ ...patch, scheme: "custom" })
  const isTps = value.scheme === "tps_2015"

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 rounded-lg border border-border p-1 text-xs" role="group" aria-label="Scheme">
        <button
          type="button"
          onClick={() => set({ ...TPS_PRESET })}
          className={cn("flex-1 rounded-md px-2 py-1", isTps ? "bg-muted text-ink" : "text-ink-2 hover:text-ink")}
        >
          Teachers' Pension (TPS)
        </button>
        <button
          type="button"
          onClick={() => set({ scheme: "custom" })}
          className={cn("flex-1 rounded-md px-2 py-1", !isTps ? "bg-muted text-ink" : "text-ink-2 hover:text-ink")}
        >
          Other scheme
        </button>
      </div>

      <p className="text-xs text-ink-muted">From your latest annual benefit statement.</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Pension built up (a year)</Label>
          <MoneyInput value={value.accruedAnnualPension} onChange={(v) => set({ accruedAnnualPension: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Statement date</Label>
          <DateInput value={value.accruedAsOf} onChange={(v) => set({ accruedAsOf: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Pensionable salary</Label>
          <MoneyInput value={value.pensionableSalary} onChange={(v) => set({ pensionableSalary: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Salary growth a year</Label>
          <PercentInput value={value.salaryGrowthRate} onChange={(v) => set({ salaryGrowthRate: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Lump sum built up</Label>
          <MoneyInput value={value.accruedLumpSum} onChange={(v) => set({ accruedLumpSum: v })} />
        </div>
        <div className="flex flex-col justify-end gap-1.5">
          <div className="flex h-8 items-center justify-between gap-2">
            <Label htmlFor="db-active">Still building up</Label>
            <Switch
              id="db-active"
              checked={value.isActiveMember}
              onCheckedChange={(checked) => set({ isActiveMember: checked })}
            />
          </div>
        </div>
      </div>

      <p className="pt-1 text-xs text-ink-muted">Scheme rules</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Build-up rate (1 / n of salary)</Label>
          <Input
            type="number"
            min={1}
            value={value.accrualDenominator ?? ""}
            onChange={(e) => setRule({ accrualDenominator: numberOrUndefined(e.target.value) })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Revaluation above CPI</Label>
          <PercentInput value={value.revaluationAboveCpi} onChange={(v) => setRule({ revaluationAboveCpi: v })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Pension age</Label>
          <Input
            type="number"
            min={50}
            max={75}
            value={value.normalPensionAge ?? ""}
            onChange={(e) => setRule({ normalPensionAge: numberOrUndefined(e.target.value) })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Value as × yearly pension</Label>
          <Input
            type="number"
            min={1}
            max={40}
            value={value.capitalisationFactor ?? ""}
            onChange={(e) => set({ capitalisationFactor: numberOrUndefined(e.target.value) })}
          />
        </div>
      </div>
    </div>
  )
}
