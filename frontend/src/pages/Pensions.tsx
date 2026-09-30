import { useState } from "react"
import { Link } from "react-router"
import { useAccount, useAccountHistories, useAccounts, type AccountSummary } from "@/api/hooks/useAccounts"
import { usePeople } from "@/api/hooks/usePeople"
import { useProjection, useProjectionsForPeople } from "@/api/hooks/useProjection"
import { useAllowances, useRecurringPlans } from "@/api/hooks/useRecurring"
import { useSettings } from "@/api/hooks/useSettings"
import { AccountFormDialog } from "@/components/AccountFormDialog"
import { AllowanceMeters } from "@/components/AllowanceMeters"
import { CurrentVsProjectedChart } from "@/components/charts/CurrentVsProjectedChart"
import { EmptyState } from "@/components/EmptyState"
import { HistoryProjectionControls } from "@/components/HistoryProjectionControls"
import { type HorizonYears } from "@/components/HorizonToggle"
import { Money } from "@/components/Money"
import { PersonAvatar } from "@/components/PersonAvatar"
import { StalenessBadge } from "@/components/StalenessBadge"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/PageHeader"
import { Plus } from "lucide-react"
import { WRAPPER_LABELS } from "@/lib/categories"
import { ALL_HISTORY_FROM, formatDate, rangeStartIso, type ChartRange } from "@/lib/dates"
import { birthdayAtAge, monthsUntil } from "@/lib/pension"
import { projectedEndValue, sumHistories, sumProjectionAccounts } from "@/lib/series"

const PENSION_COLOR = "var(--chart-2, #eb6834)"
const DEFAULT_PENSION_ACCESS_AGE = 57

export function Pensions() {
  const { data: accounts } = useAccounts({ category: "pension" })
  const { data: people } = usePeople()
  const { data: allowances } = useAllowances()
  const { data: settings } = useSettings()
  const [horizon, setHorizon] = useState<HorizonYears>(20)
  const [range, setRange] = useState<ChartRange>("All")
  const [showProjection, setShowProjection] = useState(true)
  const [addOpen, setAddOpen] = useState(false)

  const pensionAccounts = accounts ?? []
  const accountIds = pensionAccounts.map((a) => a.id)

  // Household chart: one projection over the chosen horizon, summed across pension accounts only.
  const { data: projection } = useProjection({ months: horizon * 12, byAccount: true })
  // "All" has no range start, so ask for everything rather than the server's one-year default.
  const histories = useAccountHistories(accountIds, rangeStartIso(range) ?? ALL_HISTORY_FROM)

  // "Projected pot at retirement" needs each person run to *their* retirement date, so this is a
  // projection per person rather than one household projection.
  const peopleWithDob = (people ?? []).filter((p) => p.date_of_birth)
  const retirementRequests = peopleWithDob.map((p) => ({
    personId: p.id,
    months: monthsUntil(birthdayAtAge(p.date_of_birth!, p.retirement_age)),
  }))
  const retirementProjections = useProjectionsForPeople(retirementRequests)

  if (!accounts) return null

  const householdTotal = pensionAccounts.reduce((sum, a) => sum + a.scoped_value_gbp, 0)

  // Each person's pension accounts valued at their own retirement date, then added up.
  const projectedAtRetirement = peopleWithDob.reduce((sum, person, i) => {
    const byAccount = retirementProjections[i]?.data?.by_account
    const personAccountIds = pensionAccounts
      .filter((a) => a.owners.some((o) => o.person_id === person.id))
      .map((a) => a.id)
    return (
      sum +
      personAccountIds.reduce((s, id) => s + (projectedEndValue(byAccount, id) ?? 0), 0)
    )
  }, 0)

  if (pensionAccounts.length === 0) {
    return (
      <div className="flex flex-col gap-10">
        <PageHeader eyebrow="Every pension in the household" title="Pensions" />
        <EmptyState
          title="No pensions yet"
          description="Add a SIPP or workplace pension to track the pot, contributions and what it's projected to be worth at retirement."
          action={
            <Button size="sm" onClick={() => setAddOpen(true)}>
              Add pension
            </Button>
          }
        />
        <AccountFormDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          dialogTitle="Add pension"
          defaultCategory="pension"
          defaultWrapper="sipp"
        />
      </div>
    )
  }

  const history = sumHistories(
    histories.map((q) => q.data ?? []).filter((h) => h.length > 0)
  )
  const projectionValues = sumProjectionAccounts(
    projection?.by_account,
    accountIds,
    projection?.dates.length ?? 0
  )

  const accessAge = (settings?.pension_access_age as number | undefined) ?? DEFAULT_PENSION_ACCESS_AGE

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="Every pension in the household"
        title="Pensions"
        actions={
          <Button variant="outline" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" />
            Add pension
          </Button>
        }
      />

      <section className="grid grid-cols-2 gap-x-8 gap-y-6 lg:grid-cols-3" aria-label="Summary">
        <StatTile
          label="Household pensions"
          value={<Money value={householdTotal} whole />}
          hint={`${pensionAccounts.length} account${pensionAccounts.length === 1 ? "" : "s"}`}
        />
        <StatTile
          label="Projected at retirement"
          value={<Money value={projectedAtRetirement} whole />}
          hint={
            peopleWithDob.length > 0
              ? "Each person at their own retirement age"
              : "Add a date of birth to project"
          }
        />
      </section>

      <section aria-label="Pension value chart">
          <CurrentVsProjectedChart
            historyDates={history.dates}
            historyValues={history.values}
            projectionDates={projection?.dates ?? []}
            projectionValues={projectionValues}
            label="Pension value"
            color={PENSION_COLOR}
            historyFrom={rangeStartIso(range)}
            showProjection={showProjection}
            headerActions={
              <HistoryProjectionControls
                range={range}
                onRangeChange={setRange}
                showProjection={showProjection}
                onShowProjectionChange={setShowProjection}
                horizon={horizon}
                onHorizonChange={setHorizon}
              />
            }
          />
      </section>

      <div className="grid grid-cols-1 gap-x-14 gap-y-10 lg:grid-cols-2">
      {(people ?? []).map((person) => {
        const personAccounts = pensionAccounts.filter((a) =>
          a.owners.some((o) => o.person_id === person.id)
        )
        if (personAccounts.length === 0) return null
        const index = peopleWithDob.findIndex((p) => p.id === person.id)
        return (
          <PersonPensionGroup
            key={person.id}
            person={person}
            accounts={personAccounts}
            accessAge={accessAge}
            allowance={(allowances ?? []).filter((a) => a.person_id === person.id)}
            retirementByAccount={
              index >= 0 ? retirementProjections[index]?.data?.by_account : undefined
            }
          />
        )
      })}
      </div>

      <AccountFormDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        dialogTitle="Add pension"
        defaultCategory="pension"
      />
    </div>
  )
}

type Person = NonNullable<ReturnType<typeof usePeople>["data"]>[number]
type AllowanceRows = NonNullable<ReturnType<typeof useAllowances>["data"]>

function PersonPensionGroup({
  person,
  accounts,
  accessAge,
  allowance,
  retirementByAccount,
}: {
  person: Person
  accounts: AccountSummary[]
  accessAge: number
  allowance: AllowanceRows
  retirementByAccount: Record<string, number[]> | null | undefined
}) {
  const total = accounts.reduce((sum, a) => sum + a.scoped_value_gbp, 0)
  const accessDate = person.date_of_birth ? birthdayAtAge(person.date_of_birth, accessAge) : null
  const retirementDate = person.date_of_birth
    ? birthdayAtAge(person.date_of_birth, person.retirement_age)
    : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-3">
          <PersonAvatar name={person.name} color={person.color} />
          <span>{person.name}</span>
        </CardTitle>
        <CardAction>
          <Money value={total} whole className="font-heading text-[22px] text-ink" />
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          <StatTile
            compact
            label={`Pension access (age ${accessAge})`}
            value={accessDate ? formatDate(accessDate) : "—"}
            hint={person.date_of_birth ? undefined : "Add a date of birth in Settings"}
          />
          <StatTile
            compact
            label={`Retirement (age ${person.retirement_age})`}
            value={retirementDate ? formatDate(retirementDate) : "—"}
          />
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-2 text-[13px] text-ink-2">Annual allowance this tax year</p>
            <AllowanceMeters
              allowances={allowance}
              kind="pension"
              showRemaining
              emptyNote="No allowance data for this tax year."
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {accounts.map((account) => (
            <PensionAccountCard
              key={account.id}
              account={account}
              projectedAtRetirement={projectedEndValue(retirementByAccount, account.id)}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function PensionAccountCard({
  account,
  projectedAtRetirement,
}: {
  account: AccountSummary
  projectedAtRetirement: number | undefined
}) {
  const { data: plans } = useRecurringPlans({ accountId: account.id })

  // Contribution split derived from this account's recurring plans, exactly as the Person page's
  // pensions tab did: plans carry their source, and tax relief is a rate applied to the amount.
  const split = new Map<string, number>()
  for (const plan of plans ?? []) {
    const source = plan.contribution_source ?? "personal"
    split.set(source, (split.get(source) ?? 0) + plan.amount_gbp)
    const relief = plan.amount_gbp * (plan.tax_relief_rate ?? 0)
    if (relief > 0) split.set("tax_relief", (split.get("tax_relief") ?? 0) + relief)
  }

  return (
    <Card variant="boxed" className="h-full">
      <CardContent className="flex flex-col gap-2.5">
        <Link to={`/accounts/${account.id}`} className="flex items-center gap-2">
          <span className="flex-1 truncate text-[15px] font-medium text-ink hover:underline">{account.name}</span>
          {account.wrapper !== "none" && (
            <span className="shrink-0 rounded border border-brass px-1.5 py-px text-[11px] font-semibold tracking-wider text-brass">
              {WRAPPER_LABELS[account.wrapper]}
            </span>
          )}
        </Link>
        <p className="text-[28px] leading-tight text-ink">
          <Money value={account.scoped_value_gbp} display whole />
        </p>
        {account.valuation_method === "defined_benefit" ? (
          <DbPensionIncome accountId={account.id} />
        ) : (
          <p className="text-xs text-ink-muted">
            Projected at retirement:{" "}
            {projectedAtRetirement === undefined ? (
              "—"
            ) : (
              <Money value={Math.abs(projectedAtRetirement)} />
            )}
          </p>
        )}
        {split.size > 0 && (
          <div className="flex flex-col gap-0.5 border-t border-rule-soft pt-2 text-xs text-ink-muted">
            <span className="text-ink-2">Monthly contributions</span>
            {Array.from(split.entries()).map(([source, amount]) => (
              <div key={source} className="flex justify-between">
                <span className="capitalize">{source.replace("_", " ")}</span>
                <Money value={amount} />
              </div>
            ))}
          </div>
        )}
        {account.detail && <p className="text-xs text-warn">{account.detail}</p>}
        <StalenessBadge
          staleness={account.staleness as "ok" | "warn" | "alert"}
          daysSince={account.days_since_update ?? null}
          prices={account.valuation_method === "holdings"}
          className="self-start"
        />
      </CardContent>
    </Card>
  )
}

/** A DB pension has no pot to project: show the income it pays instead. */
function DbPensionIncome({ accountId }: { accountId: number }) {
  const { data: account } = useAccount(accountId)
  const summary = account?.db_pension_summary
  if (!summary) return null
  return (
    <div className="flex flex-col gap-0.5 text-xs text-ink-muted">
      <span>
        <Money value={summary.annual_pension_today_gbp} /> a year built up so far
      </span>
      {summary.pension_start_date && summary.annual_pension_at_start_today_money_gbp != null && (
        <span>
          About <Money value={summary.annual_pension_at_start_today_money_gbp} /> a year from{" "}
          {formatDate(summary.pension_start_date)}, in today&apos;s money
        </span>
      )}
    </div>
  )
}
