import { useQueryClient } from "@tanstack/react-query"
import { Plus, Settings2 } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"
import { useAccount, useAccountHistory, useAccounts } from "@/api/hooks/useAccounts"
import { useEquity, useSchedule } from "@/api/hooks/useLoans"
import { useProjection } from "@/api/hooks/useProjection"
import { AccountFormDialog } from "@/components/AccountFormDialog"
import type { OwnerShareValue } from "@/components/OwnersEditor"
import { EmptyState } from "@/components/EmptyState"
import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { StatTile } from "@/components/StatTile"
import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/PageHeader"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatDate } from "@/lib/dates"
import { fixEndsHint } from "@/lib/property"
import { ValueVsBalanceChart } from "@/components/property/ValueVsBalanceChart"
import { SimulatorCard } from "@/components/property/SimulatorCard"
import { RatePeriodsCard } from "@/components/property/RatePeriodsCard"
import { ScheduleCard } from "@/components/property/ScheduleCard"
import { ValuationsCard } from "@/components/property/ValuationsCard"

/** 30 years — long enough to cover a full remaining mortgage term on the same axis. */
const PROJECTION_MONTHS = 360

export function Property() {
  const { data: properties } = useAccounts({ category: "property" })
  const [addOpen, setAddOpen] = useState(false)

  if (!properties) return null

  if (properties.length === 0) {
    return (
      <div className="flex flex-col gap-10">
        <PageHeader eyebrow="Your home and what’s owed on it" title="Property &amp; mortgage" />
        <EmptyState
          title="No property yet"
          description="Add your home to track its value, mortgage and equity."
          action={
            <Button size="sm" onClick={() => setAddOpen(true)}>
              Add property
            </Button>
          }
        />
        <AccountFormDialog open={addOpen} onOpenChange={setAddOpen} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="Property &amp; mortgage"
        title={properties.length === 1 ? properties[0].name : "Property & mortgage"}
        description={
          properties.length === 1 && properties[0].owners.length > 0
            ? `Owned by ${properties[0].owners.map((o) => o.name).join(" and ")}.`
            : undefined
        }
        actions={
          <Button variant="outline" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" />
            Add property
          </Button>
        }
      />

      {properties.length > 1 ? (
        <Tabs defaultValue={String(properties[0].id)}>
          <TabsList>
            {properties.map((p) => (
              <TabsTrigger key={p.id} value={String(p.id)}>
                {p.name}
              </TabsTrigger>
            ))}
          </TabsList>
          {properties.map((p) => (
            <TabsContent key={p.id} value={String(p.id)} className="mt-8">
              <PropertyPanel propertyId={p.id} />
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <PropertyPanel propertyId={properties[0].id} />
      )}

      <AccountFormDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

function PropertyPanel({ propertyId }: { propertyId: number }) {
  const { data: property } = useAccount(propertyId)
  const { data: equity } = useEquity(propertyId)
  // `/history` defaults to the last 365 days, which would clip the chart to one year and hide the
  // point of owning a purchase-date anchor. Ask from the purchase date so the value line runs from
  // completion, and use the same window for the mortgage so the two are directly comparable.
  const historyFrom = property?.property?.purchase_date ?? undefined
  const { data: history } = useAccountHistory(propertyId, historyFrom)
  const primaryLoanId = equity?.loans[0]?.account_id
  const { data: loanHistory } = useAccountHistory(primaryLoanId, historyFrom)
  const { data: schedule } = useSchedule(primaryLoanId)
  // The property's future value comes from the same per-account projection the Pensions and
  // Investments pages use, so its growth model (and any scenario property-growth override) is
  // applied once, in the backend. 360 months covers a full mortgage term.
  const { data: projection } = useProjection({ months: PROJECTION_MONTHS, byAccount: true })
  const [addMortgageOpen, setAddMortgageOpen] = useState(false)
  const queryClient = useQueryClient()

  if (!property || !equity) return <p className="text-sm text-ink-muted">Loading…</p>

  const summary = schedule?.summary
  const totalOwed = equity.loans.reduce((sum, l) => sum + l.owed_gbp, 0)
  const propertyOwners: OwnerShareValue[] = property.owners.map((o) => ({
    personId: o.person_id,
    share: o.share,
  }))

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <div className="-mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 md:-mt-8">
        <Link
          to={`/accounts/${propertyId}`}
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink"
        >
          <Settings2 className="size-3.5" />
          Manage property account
        </Link>
        {primaryLoanId && (
          <Link
            to={`/accounts/${primaryLoanId}`}
            className="inline-flex items-center gap-1.5 text-[13px] text-ink-2 hover:text-ink"
          >
            <Settings2 className="size-3.5" />
            Manage mortgage account
          </Link>
        )}
      </div>

      <section className="grid grid-cols-2 gap-x-8 gap-y-7 lg:grid-cols-4" aria-label="Property and mortgage figures">
        <StatTile label="Property value (est.)" value={<Money value={equity.value_gbp} whole />} />
        <StatTile label="Mortgage owed (est.)" value={<Money value={totalOwed} whole />} />
        <StatTile
          label="Equity"
          value={<Money value={equity.equity_gbp} whole />}
          hint={
            equity.by_person.length > 1 ? (
              <span className="flex flex-wrap items-center gap-x-2">
                {equity.by_person.map((row, i) => (
                  <span key={row.person_id}>
                    {i > 0 && "· "}
                    {property.owners.find((o) => o.person_id === row.person_id)?.name ?? ""}{" "}
                    <Money value={row.equity_gbp} whole />
                  </span>
                ))}
              </span>
            ) : undefined
          }
        />
        <StatTile label="Loan to value" value={equity.ltv !== null && equity.ltv !== undefined ? <Pct value={equity.ltv} decimals={1} /> : "—"} />
        <StatTile
          label="Current rate"
          value={summary ? <Pct value={summary.current_rate} decimals={2} /> : "—"}
          hint={fixEndsHint(summary)}
        />
        <StatTile label="Monthly payment" value={summary ? <Money value={summary.monthly_payment_gbp} /> : "—"} />
        <StatTile
          label="Mortgage-free"
          value={summary?.payoff_date ? formatDate(summary.payoff_date) : "—"}
        />
      </section>

      <section aria-label="Property value and mortgage balance">
          <ValueVsBalanceChart
            propertyDates={(history ?? []).map((h) => h.date)}
            propertyValues={(history ?? []).map((h) => h.value_gbp)}
            loanDates={(loanHistory ?? []).map((h) => h.date)}
            loanValues={(loanHistory ?? []).map((h) => Math.abs(h.value_gbp))}
            futureLoanRows={schedule?.rows}
            projectionDates={projection?.dates}
            projectedPropertyValues={projection?.by_account?.[String(propertyId)]}
          />
      </section>

      {primaryLoanId ? (
        <div className="grid grid-cols-1 gap-x-14 gap-y-10 xl:grid-cols-2">
          <SimulatorCard accountId={primaryLoanId} allowanceWarnings={schedule?.allowance_warnings ?? []} />
          <RatePeriodsCard accountId={primaryLoanId} />
          <div className="xl:col-span-2">
            <ScheduleCard accountId={primaryLoanId} />
          </div>
        </div>
      ) : (
        <>
          <EmptyState
            title="No mortgage linked to this property"
            description="Add the mortgage's value, term and rate — it links to this property automatically and its history and forecast plot straight away."
            action={
              <Button size="sm" onClick={() => setAddMortgageOpen(true)}>
                Add mortgage
              </Button>
            }
          />
          <AccountFormDialog
            open={addMortgageOpen}
            onOpenChange={setAddMortgageOpen}
            dialogTitle="Add mortgage"
            defaultCategory="mortgage"
            defaultWrapper="none"
            defaultMethod="amortising"
            defaultOwners={propertyOwners}
            securedOnAccountId={propertyId}
            quickMortgage
            onCreated={() => {
              // The property page already shows the newly-linked mortgage's equity/KPIs/chart
              // immediately below, so stay put rather than navigating to the new account.
              setAddMortgageOpen(false)
              queryClient.invalidateQueries({ queryKey: ["equity", propertyId] })
            }}
          />
        </>
      )}

      <ValuationsCard propertyId={propertyId} loanId={primaryLoanId} />
    </div>
  )
}
