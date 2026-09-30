import { useMemo, useState } from "react"
import { toast } from "sonner"
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { useAccounts } from "@/api/hooks/useAccounts"
import { usePeople } from "@/api/hooks/usePeople"
import {
  useCreateScenarioEvent,
  useDeleteScenarioEvent,
  useMonteCarlo,
  useProjection,
  useProjectionCompare,
  useScenarioEvents,
  useUpdateScenarioEvent,
  useScenarios,
  type ScenarioEventIn,
  type ScenarioEventOut,
} from "@/api/hooks/useProjection"
import { useRecurringPlans } from "@/api/hooks/useRecurring"
import { usePatchSettings, useSettings } from "@/api/hooks/useSettings"
import { InlinePercentInput } from "@/components/InlinePercentInput"
import { Money } from "@/components/Money"
import { AreaStackChart } from "@/components/charts/AreaStackChart"
import { FanChart } from "@/components/charts/FanChart"
import { ChartCard, type ChartCardSeries } from "@/components/charts/ChartCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tooltip as HelpTip } from "@/components/ui/tooltip"
import { PageHeader } from "@/components/PageHeader"
import { Segmented } from "@/components/Segmented"
import { DateInput } from "@/components/DateInput"
import { Label } from "@/components/ui/label"
import { MoneyInput } from "@/components/MoneyInput"
import { PercentInput } from "@/components/PercentInput"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { apiErrorMessage } from "@/lib/api-error"
import { CATEGORY_COLORS, CATEGORY_LABELS, type Category } from "@/lib/categories"
import { formatDate, todayIso } from "@/lib/dates"
import { FAN_LEGEND, buildFanRows, fanSummary } from "@/lib/fan"
import { formatUnits } from "@/lib/format"
import { useTheme } from "@/lib/theme"

const SLOT_COLORS: { light: string; dark: string }[] = [
  { light: "#2a78d6", dark: "#3987e5" },
  { light: "#eb6834", dark: "#d95926" },
  { light: "#1baf7a", dark: "#199e70" },
  { light: "#eda100", dark: "#c98500" },
  { light: "#e87ba4", dark: "#d55181" },
  { light: "#008300", dark: "#008300" },
  { light: "#4a3aa7", dark: "#9085e9" },
  { light: "#e34948", dark: "#e66767" },
]

const EVENT_KIND_LABELS: Record<ScenarioEventIn["kind"], string> = {
  lump_sum: "Lump sum",
  stop_plan: "Stop Regular Payment",
  change_plan_amount: "Change Regular Payment amount",
  set_return_rate: "Set return rate",
}

// Hover help for the Assumptions card. Keep in step with projection_service._build_account.
const INFLATION_HELP =
  "Doesn't grow or shrink any account. It converts future values into today's money when real terms is on, " +
  "and sets how fast defined benefit pensions are revalued. A scenario can override it."

const RETURN_RATE_HELP: Record<string, string> = {
  equity: "Expected yearly return on shares and equity funds held in your investment accounts.",
  bond: "Expected yearly return on bonds, gilts and bond funds held in your investment accounts.",
  multi_asset:
    "Expected yearly return on mixed funds held in your investment accounts. Also used for investment and " +
    "pension accounts tracked by balance only, unless the account has its own rate.",
  property:
    "Yearly growth for your properties, unless the property has its own growth rate or the scenario sets one. " +
    "Also used for property funds and REITs held in your investment accounts.",
  commodity: "Expected yearly return on gold and other commodity funds held in your investment accounts.",
  cash: "Interest on cash accounts that don't have their own interest rate, and on cash-like funds.",
  crypto: "Expected yearly return on crypto held in your investment accounts.",
  other: "Expected yearly return on anything held in your investment accounts that doesn't fit another class.",
}

const VOLATILITY_GENERIC =
  "How much this asset class swings from year to year. Higher numbers widen the range of outcomes; " +
  "it doesn't change the main projection line."

const VOLATILITY_HELP: Record<string, string> = {
  multi_asset: VOLATILITY_GENERIC + " Also used for accounts tracked by balance only.",
  property:
    VOLATILITY_GENERIC + " Applies to property funds in your investments only. Your home's value isn't varied.",
  cash: "Cash accounts don't swing in value, so this is normally 0%.",
}

function nearestIndexForYears(dates: string[], years: number): number {
  const target = new Date()
  target.setFullYear(target.getFullYear() + years)
  const targetIso = target.toISOString().slice(0, 10)
  let best = 0
  for (let i = 0; i < dates.length; i++) {
    if (dates[i] <= targetIso) best = i
    else break
  }
  return best
}

export function Projections() {
  const theme = useTheme()
  const { data: people } = usePeople()
  const { data: scenarios } = useScenarios()
  const { data: accounts } = useAccounts()
  const { data: settings } = useSettings()
  const { data: allPlans } = useRecurringPlans()

  const [scope, setScope] = useState<number | null>(null)
  const [years, setYears] = useState(30)
  const [scenarioId, setScenarioId] = useState<number | undefined>(undefined)
  const [realTerms, setRealTerms] = useState(false)
  const [splitMode, setSplitMode] = useState<"category" | "person">("category")
  const [includeProperty, setIncludeProperty] = useState(true)
  const [compareIds, setCompareIds] = useState<number[]>([])
  const [showAssumptions, setShowAssumptions] = useState(false)

  const months = years * 12
  const defaultScenario = scenarios?.find((s) => s.is_default)
  const activeScenarioId = scenarioId ?? defaultScenario?.id

  const { data: projection, isLoading } = useProjection({
    personId: scope ?? undefined,
    scenarioId: activeScenarioId,
    months,
    realTerms,
    byAccount: false,
  })

  const { data: monteCarlo, isLoading: monteCarloLoading } = useMonteCarlo({
    personId: scope ?? undefined,
    scenarioId: activeScenarioId,
    months,
    realTerms,
    enabled: activeScenarioId !== undefined,
  })

  const compareScenarioIds = compareIds.length > 0 ? compareIds : (scenarios ?? []).slice(0, 3).map((s) => s.id)
  const { data: compare } = useProjectionCompare({
    scenarioIds: compareScenarioIds,
    personId: scope ?? undefined,
    months,
    realTerms,
  })

  const dates = projection?.dates ?? []
  const total = projection?.total ?? []

  const categorySeries: ChartCardSeries[] = Object.entries(projection?.by_category ?? {}).map(
    ([key, values]) => ({
      key,
      label: CATEGORY_LABELS[key as Category] ?? key,
      color: CATEGORY_COLORS[key as Category]?.[theme] ?? "var(--ink-muted)",
      values: values as number[],
    })
  )

  const filteredCategorySeries = includeProperty
    ? categorySeries
    : categorySeries.filter((s) => s.key !== "property")

  const propertyValues = (projection?.by_category?.property as number[] | undefined) ?? []
  const adjustedTotal = includeProperty
    ? total
    : total.map((t, i) => t - (propertyValues[i] ?? 0))

  const fanRows = monteCarlo ? buildFanRows(monteCarlo, includeProperty ? [] : propertyValues) : []
  const fanRange = fanSummary(fanRows)
  const fanTableSeries: ChartCardSeries[] = [
    { key: "p90", label: "90th", color: "var(--accent)", values: fanRows.map((r) => r.outer[1]) },
    { key: "p50", label: "Median", color: "var(--accent)", values: fanRows.map((r) => r.median) },
    { key: "p10", label: "10th", color: "var(--accent)", values: fanRows.map((r) => r.outer[0]) },
    { key: "plan", label: "Projection", color: "var(--ink)", values: fanRows.map((r) => r.plan) },
  ]

  const personSeries: ChartCardSeries[] = (people ?? []).map((p, i) => ({
    key: String(p.id),
    label: p.name,
    color: SLOT_COLORS[i % SLOT_COLORS.length][theme],
    values: (projection?.by_person?.[p.id] as number[] | undefined) ?? [],
  }))

  const milestoneMarkers = (projection?.milestones ?? []).slice(0, 6).map((m) => ({
    date: m.date,
    label: m.label,
  }))

  // Table: values at 1, 5, 10, 20, 30 years and at each person's retirement age.
  const horizonRows =
    dates.length === 0
      ? []
      : [1, 5, 10, 20, 30]
          .filter((y) => y <= years)
          .map((y) => {
            const idx = nearestIndexForYears(dates, y)
            return { label: `${y} year${y === 1 ? "" : "s"}`, value: adjustedTotal[idx] ?? 0, date: dates[idx] }
          })
  const retirementRows =
    dates.length === 0
      ? []
      : (people ?? [])
          .filter((p) => p.date_of_birth)
          .map((p) => {
            const milestone = (projection?.milestones ?? []).find(
              (m) => m.kind === "retirement" && m.person_id === p.id
            )
            if (!milestone) return null
            const idx = dates.findIndex((d) => d >= milestone.date)
            const safeIdx = idx === -1 ? dates.length - 1 : idx
            return { label: `${p.name}'s retirement`, value: adjustedTotal[safeIdx] ?? 0, date: milestone.date }
          })
          .filter((r): r is { label: string; value: number; date: string } => r !== null)

  // Contributions vs growth (approximation: growth = total change beyond today's value and
  // cumulative contributions — see report for the judgment call this simplifies).
  const contributions = projection?.contributions ?? []
  const growthSeries = adjustedTotal.map((t, i) => Math.max(0, t - (adjustedTotal[0] ?? 0) - (contributions[i] ?? 0)))
  const contribGrowthData = dates.map((d, i) => ({
    date: d,
    Contributions: contributions[i] ?? 0,
    Growth: growthSeries[i] ?? 0,
  }))

  const compareLineData = useMemo(() => {
    if (!compare) return []
    return compare.dates.map((d, i) => {
      const row: Record<string, number | string> = { date: d }
      for (const s of compare.series) row[s.name] = s.total[i] ?? 0
      return row
    })
  }, [compare])

  const defaultRates = (settings?.default_return_rates as Record<string, number> | undefined) ?? {}
  const defaultVolatility = (settings?.default_volatility as Record<string, number> | undefined) ?? {}
  const inflationRate = (settings?.inflation_rate as number | undefined) ?? 0.025
  const patchSettings = usePatchSettings()

  async function saveSetting(patch: Record<string, unknown>) {
    try {
      await patchSettings.mutateAsync(patch)
      toast.success("Assumption updated")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not save that assumption"))
    }
  }

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="Where today’s plans lead"
        title="Projections"
        description="Every account grown at its expected return, with your regular payments added, from today onwards."
      />

      <section
        aria-label="Projection settings"
        className="flex flex-wrap items-end gap-x-7 gap-y-4 border-y border-border py-5"
      >
          <Segmented
            label="Scope"
            options={[{ value: null, label: "Household" }, ...(people ?? []).map((p) => ({ value: p.id, label: p.name }))]}
            value={scope}
            onChange={setScope}
          />

          <div className="flex min-w-48 flex-col gap-1.5">
            <Label className="text-[13px] text-ink-2">Horizon · {years} years</Label>
            <Slider
              min={1}
              max={50}
              step={1}
              value={[years]}
              onValueChange={(v) => setYears(Array.isArray(v) ? v[0] : v)}
              className="w-48"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-[13px] text-ink-2">Scenario</Label>
            <Select value={String(activeScenarioId ?? "")} onValueChange={(v) => setScenarioId(Number(v))}>
              <SelectTrigger className="w-40">
                <SelectValue>{() => scenarios?.find((s) => s.id === activeScenarioId)?.name ?? "Base"}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {(scenarios ?? []).map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Segmented
            label="Money"
            options={[
              { value: false, label: "Nominal" },
              { value: true, label: "Today’s money" },
            ]}
            value={realTerms}
            onChange={setRealTerms}
          />

          <Segmented
            label="Split by"
            options={[
              { value: "category" as const, label: "Category" },
              { value: "person" as const, label: "Person" },
            ]}
            value={splitMode}
            onChange={setSplitMode}
          />

          <label className="flex h-8 items-center gap-2 text-[13px] text-ink-2">
            <input
              type="checkbox"
              checked={includeProperty}
              onChange={(e) => setIncludeProperty(e.target.checked)}
            />
            Include property
          </label>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Projected net worth</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="py-16 text-center text-sm text-ink-muted">Calculating…</p>
          ) : (
            <ChartCard
              dates={dates}
              series={splitMode === "category" ? filteredCategorySeries : personSeries}
            >
              <AreaStackChart
                dates={dates}
                total={adjustedTotal}
                series={splitMode === "category" ? filteredCategorySeries : personSeries}
                milestones={milestoneMarkers}
                height={340}
              />
            </ChartCard>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Range of outcomes</CardTitle>
          <p className="text-sm text-ink-2">
            {fanRange ? (
              <>
                Markets won't follow the projection exactly. In {formatUnits(monteCarlo?.paths ?? 0)}{" "}
                simulated markets, 8 in 10 ended between <Money value={fanRange.low} compact /> and{" "}
                <Money value={fanRange.high} compact /> in {years} years; the median was{" "}
                <Money value={fanRange.median} compact />.
              </>
            ) : (
              "How far markets could move the projection either way."
            )}
          </p>
        </CardHeader>
        <CardContent>
          {monteCarloLoading ? (
            <p className="py-16 text-center text-sm text-ink-muted">Simulating…</p>
          ) : (
            <ChartCard dates={monteCarlo?.dates ?? []} series={fanTableSeries} legend={FAN_LEGEND}>
              <FanChart rows={fanRows} />
            </ChartCard>
          )}
          <p className="mt-3 text-xs text-ink-muted">
            Investments and pensions vary by the volatility of what they hold (set under Assumptions);
            cash, property, loans and defined benefit pensions follow the projection.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Values at key horizons</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col divide-y divide-border p-0">
            {[...horizonRows, ...retirementRows].map((row) => (
              <div key={row.label} className="flex items-center justify-between px-4 py-2 text-sm">
                <div>
                  <p className="text-ink">{row.label}</p>
                  <p className="text-xs text-ink-muted">{formatDate(row.date)}</p>
                </div>
                <Money value={row.value} className="text-ink" />
              </div>
            ))}
            {horizonRows.length === 0 && retirementRows.length === 0 && (
              <p className="px-4 py-4 text-sm text-ink-muted">No milestones in this horizon yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Contributions vs growth</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartCard
              dates={dates}
              series={[
                { key: "contributions", label: "Contributions", color: SLOT_COLORS[0][theme], values: contributions },
                { key: "growth", label: "Growth", color: SLOT_COLORS[1][theme], values: growthSeries },
              ]}
            >
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={contribGrowthData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke="var(--grid)" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickFormatter={(d) => formatDate(d)}
                      stroke="var(--axis)"
                      tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
                      minTickGap={40}
                    />
                    <YAxis
                      stroke="var(--axis)"
                      tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
                      width={64}
                    />
                    <Tooltip
                      formatter={(v) => Number(v).toLocaleString("en-GB", { style: "currency", currency: "GBP" })}
                      labelFormatter={(d) => formatDate(String(d))}
                    />
                    <Line
                      type="monotone"
                      dataKey="Contributions"
                      stroke={SLOT_COLORS[0][theme]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="Growth"
                      stroke={SLOT_COLORS[1][theme]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Scenario comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex flex-wrap gap-3 text-xs">
            {(scenarios ?? []).map((s, i) => {
              const selected = compareScenarioIds.includes(s.id)
              return (
                <label key={s.id} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={selected && compareIds.length === 0 && compareScenarioIds.length <= 1}
                    onChange={(e) => {
                      const next = new Set(compareIds.length > 0 ? compareIds : compareScenarioIds)
                      if (e.target.checked) {
                        if (next.size < 3) next.add(s.id)
                      } else {
                        next.delete(s.id)
                      }
                      setCompareIds(Array.from(next))
                    }}
                  />
                  <span
                    className="size-2.5 rounded-full"
                    style={{ backgroundColor: SLOT_COLORS[i % SLOT_COLORS.length][theme] }}
                  />
                  {s.name}
                </label>
              )
            })}
          </div>
          <ChartCard
            dates={compare?.dates ?? []}
            series={(compare?.series ?? []).map((s, i) => ({
              key: String(s.scenario_id),
              label: s.name,
              color: SLOT_COLORS[i % SLOT_COLORS.length][theme],
              values: s.total,
            }))}
            hideLegend
          >
            <div style={{ height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={compareLineData} margin={{ top: 4, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(d) => formatDate(d)}
                    stroke="var(--axis)"
                    tick={{ fill: "var(--ink-muted)", fontSize: 11 }}
                    minTickGap={40}
                  />
                  <YAxis stroke="var(--axis)" tick={{ fill: "var(--ink-muted)", fontSize: 11 }} width={64} />
                  <Tooltip
                    formatter={(v) => Number(v).toLocaleString("en-GB", { style: "currency", currency: "GBP" })}
                    labelFormatter={(d) => formatDate(String(d))}
                  />
                  {(compare?.series ?? []).map((s, i) => (
                    <Line
                      key={s.scenario_id}
                      type="monotone"
                      dataKey={s.name}
                      stroke={SLOT_COLORS[i % SLOT_COLORS.length][theme]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </ChartCard>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Assumptions &amp; scenario events</CardTitle>
          <Button variant="outline" size="sm" onClick={() => setShowAssumptions((v) => !v)}>
            {showAssumptions ? "Hide" : "Show"}
          </Button>
        </CardHeader>
        {showAssumptions && (
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div className="flex flex-col gap-1">
                <p className="text-xs text-ink-muted">
                  <HelpTip content={INFLATION_HELP}>Inflation</HelpTip>
                </p>
                <InlinePercentInput
                  aria-label="Inflation"
                  value={inflationRate}
                  onCommit={(v) => saveSetting({ inflation_rate: v })}
                />
              </div>
              {Object.entries(defaultRates).map(([k, v]) => (
                <div key={k} className="flex flex-col gap-1">
                  <p className="text-xs text-ink-muted capitalize">
                    <HelpTip content={RETURN_RATE_HELP[k] ?? "Expected yearly growth for this asset class."}>
                      {k.replace("_", " ")}
                    </HelpTip>
                  </p>
                  <InlinePercentInput
                    aria-label={k.replace("_", " ")}
                    value={v}
                    onCommit={(rate) => saveSetting({ default_return_rates: { ...defaultRates, [k]: rate } })}
                  />
                </div>
              ))}
            </div>

            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-ink">Volatility (for the range of outcomes)</p>
              <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                {Object.entries(defaultVolatility).map(([k, v]) => (
                  <div key={k} className="flex flex-col gap-1">
                    <p className="text-xs text-ink-muted capitalize">
                      <HelpTip content={VOLATILITY_HELP[k] ?? VOLATILITY_GENERIC}>{k.replace("_", " ")}</HelpTip>
                    </p>
                    <InlinePercentInput
                      aria-label={`${k.replace("_", " ")} volatility`}
                      value={v}
                      onCommit={(sigma) => saveSetting({ default_volatility: { ...defaultVolatility, [k]: sigma } })}
                    />
                  </div>
                ))}
              </div>
            </div>

            {activeScenarioId && (
              <ScenarioEventsEditor
                scenarioId={activeScenarioId}
                accounts={accounts ?? []}
                plans={allPlans ?? []}
              />
            )}
          </CardContent>
        )}
      </Card>

      <p className="text-xs text-ink-muted">
        Projections are illustrations based on your assumptions, not predictions or advice.
      </p>
    </div>
  )
}

function ScenarioEventsEditor({
  scenarioId,
  accounts,
  plans,
}: {
  scenarioId: number
  accounts: { id: number; name: string }[]
  plans: { id: number; name: string }[]
}) {
  const { data: events } = useScenarioEvents(scenarioId)
  const createEvent = useCreateScenarioEvent()
  const deleteEvent = useDeleteScenarioEvent()
  const updateEvent = useUpdateScenarioEvent()

  async function saveEventRate(event: ScenarioEventOut, rate: number) {
    try {
      await updateEvent.mutateAsync({
        eventId: event.id,
        payload: {
          date: event.date,
          kind: event.kind,
          label: event.label,
          account_id: event.account_id,
          plan_id: event.plan_id,
          amount_gbp: event.amount_gbp,
          rate,
        },
      })
      toast.success("Event updated")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not update that event"))
    }
  }

  const [kind, setKind] = useState<ScenarioEventIn["kind"]>("lump_sum")
  const [date, setDate] = useState<string | undefined>(todayIso())
  const [accountId, setAccountId] = useState<number | undefined>(accounts[0]?.id)
  const [planId, setPlanId] = useState<number | undefined>(plans[0]?.id)
  const [amount, setAmount] = useState<number | undefined>(undefined)
  const [rate, setRate] = useState<number | undefined>(undefined)
  const [label, setLabel] = useState("")

  const needsAccount = kind === "lump_sum" || kind === "set_return_rate"
  const needsPlan = kind === "stop_plan" || kind === "change_plan_amount"
  const needsAmount = kind === "lump_sum" || kind === "change_plan_amount"
  const needsRate = kind === "set_return_rate"

  const canSubmit =
    date &&
    label.trim() !== "" &&
    (!needsAccount || accountId !== undefined) &&
    (!needsPlan || planId !== undefined) &&
    (!needsAmount || amount !== undefined) &&
    (!needsRate || rate !== undefined)

  async function addEvent() {
    if (!canSubmit || !date) return
    try {
      await createEvent.mutateAsync({
        scenarioId,
        payload: {
          date,
          kind,
          label,
          account_id: needsAccount ? accountId : undefined,
          plan_id: needsPlan ? planId : undefined,
          amount_gbp: needsAmount ? amount : undefined,
          rate: needsRate ? rate : undefined,
        },
      })
      toast.success("Event added")
      setLabel("")
      setAmount(undefined)
      setRate(undefined)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that event"))
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col divide-y divide-border rounded-lg border border-border">
        {(events ?? []).map((e) => (
          <div key={e.id} className="flex items-center gap-3 px-3 py-2 text-sm">
            <span className="w-24 text-ink-muted">{formatDate(e.date)}</span>
            <span className="w-40 text-ink-2">{EVENT_KIND_LABELS[e.kind]}</span>
            <span className="flex-1 truncate text-ink">{e.label}</span>
            {e.amount_gbp != null && <Money value={e.amount_gbp} />}
            {e.rate != null && (
              <InlinePercentInput
                aria-label={`${e.label} rate`}
                value={e.rate}
                onCommit={(rate) => saveEventRate(e, rate)}
              />
            )}
            <button
              type="button"
              className="text-xs text-ink-muted hover:text-loss"
              onClick={() => deleteEvent.mutate(e.id)}
            >
              Remove
            </button>
          </div>
        ))}
        {(events ?? []).length === 0 && (
          <p className="px-3 py-3 text-sm text-ink-muted">No events on this scenario yet.</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-lg border border-border p-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Kind</Label>
          <Select value={kind} onValueChange={(v) => setKind(v as ScenarioEventIn["kind"])}>
            <SelectTrigger>
              <SelectValue>{() => EVENT_KIND_LABELS[kind]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {Object.entries(EVENT_KIND_LABELS).map(([value, l]) => (
                <SelectItem key={value} value={value}>
                  {l}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Date</Label>
          <DateInput value={date} onChange={setDate} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Label</Label>
          <input
            className="h-9 rounded-md border border-border bg-transparent px-2 text-sm"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Inheritance"
          />
        </div>
        {needsAccount && (
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Account</Label>
            <Select value={String(accountId ?? "")} onValueChange={(v) => setAccountId(Number(v))}>
              <SelectTrigger>
                <SelectValue>{() => accounts.find((a) => a.id === accountId)?.name ?? "Select"}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {accounts.map((a) => (
                  <SelectItem key={a.id} value={String(a.id)}>
                    {a.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {needsPlan && (
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Regular Payment</Label>
            <Select value={String(planId ?? "")} onValueChange={(v) => setPlanId(Number(v))}>
              <SelectTrigger>
                <SelectValue>{() => plans.find((p) => p.id === planId)?.name ?? "Select"}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {plans.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {needsAmount && (
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Amount</Label>
            <MoneyInput value={amount} onChange={setAmount} />
          </div>
        )}
        {needsRate && (
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Rate</Label>
            <PercentInput value={rate} onChange={setRate} />
          </div>
        )}
        <div className="flex items-end">
          <Button size="sm" onClick={addEvent} disabled={!canSubmit || createEvent.isPending}>
            Add event
          </Button>
        </div>
      </div>
    </div>
  )
}
