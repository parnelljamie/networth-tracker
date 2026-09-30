import { useState } from "react"
import { toast } from "sonner"
import type { components } from "@/api/schema"
import { usePutDbPension } from "@/api/hooks/useDbPension"
import { DbPensionFields } from "@/components/DbPensionFields"
import { detailsFromDraft, draftFromDetails, emptyDbPensionDraft } from "@/lib/dbPension"
import { Money } from "@/components/Money"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate } from "@/lib/dates"

type AccountDetail = components["schemas"]["AccountDetail"]

/** Defined-benefit pension: what it pays and when, plus the scheme terms behind it. */
export function DbPensionTab({ account }: { account: AccountDetail }) {
  const summary = account.db_pension_summary
  const putDbPension = usePutDbPension()
  const [draft, setDraft] = useState(() =>
    account.db_pension ? draftFromDetails(account.db_pension) : emptyDbPensionDraft()
  )
  const payload = detailsFromDraft(draft)

  async function save() {
    if (!payload) return
    try {
      await putDbPension.mutateAsync({ accountId: account.id, payload })
      toast.success("Scheme details saved")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save the scheme details"))
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {summary && (
        <Card>
          <CardContent className="grid grid-cols-2 gap-4 pt-4 sm:grid-cols-4">
            <StatTile
              label="Pension built up today"
              value={<Money value={summary.annual_pension_today_gbp} />}
              hint="a year"
            />
            <StatTile
              label="Pension starts"
              value={summary.pension_start_date ? formatDate(summary.pension_start_date) : "—"}
              hint={summary.pension_start_date ? undefined : "Add a date of birth for this person"}
            />
            <StatTile
              label="Projected at start"
              value={<Money value={summary.annual_pension_at_start_today_money_gbp ?? 0} />}
              hint="a year, in today's money"
            />
            <StatTile
              label="Projected at start"
              value={<Money value={summary.annual_pension_at_start_gbp ?? 0} />}
              hint="a year, in future money"
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Scheme details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <DbPensionFields value={draft} onChange={setDraft} />
          <p className="text-xs text-ink-muted">
            Counted in net worth as the yearly pension × the value multiple, plus any lump sum. It
            grows by CPI plus the revaluation rate while building up, then CPI only.
          </p>
          <div className="flex justify-end">
            <Button size="sm" onClick={save} disabled={!payload || putDbPension.isPending}>
              Save
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
