import { useState } from "react"
import { toast } from "sonner"
import { useAccounts } from "@/api/hooks/useAccounts"
import {
  type GoalCreate,
  type GoalScope,
  useCreateGoal,
  useDeleteGoal,
  useGoals,
} from "@/api/hooks/useGoals"
import { usePeople } from "@/api/hooks/usePeople"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/PageHeader"
import { DateInput } from "@/components/DateInput"
import { EmptyState } from "@/components/EmptyState"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { apiErrorMessage } from "@/lib/api-error"
import { CATEGORY_LABELS, type Category } from "@/lib/categories"
import { formatDate } from "@/lib/dates"

const SCOPES: { value: GoalScope; label: string }[] = [
  { value: "household", label: "Household" },
  { value: "person", label: "Person" },
  { value: "account", label: "Account" },
  { value: "category", label: "Category" },
]

const CATEGORY_OPTIONS: Category[] = [
  "investment",
  "pension",
  "cash",
  "property",
  "other_asset",
]

/** docs/05-ui.md · docs/02-data-model.md "goals" · docs/03-domain-logic.md §9 "Goals":
 * progress = scoped current value / target; projected hit date via the projection engine. */
export function Goals() {
  const { data: goals, isLoading } = useGoals()
  const { data: people } = usePeople()
  const { data: accounts } = useAccounts()
  const createGoal = useCreateGoal()
  const deleteGoal = useDeleteGoal()

  const [name, setName] = useState("")
  const [target, setTarget] = useState<number | undefined>(undefined)
  const [targetDate, setTargetDate] = useState<string | undefined>(undefined)
  const [scope, setScope] = useState<GoalScope>("household")
  const [personId, setPersonId] = useState<number | undefined>(undefined)
  const [accountId, setAccountId] = useState<number | undefined>(undefined)
  const [category, setCategory] = useState<Category | undefined>(undefined)

  function resetForm() {
    setName("")
    setTarget(undefined)
    setTargetDate(undefined)
    setScope("household")
    setPersonId(undefined)
    setAccountId(undefined)
    setCategory(undefined)
  }

  async function addGoal() {
    if (!name.trim() || !target) return
    const payload: GoalCreate = {
      name: name.trim(),
      target_gbp: target,
      target_date: targetDate ?? null,
      scope,
      person_id: scope === "person" ? personId ?? null : null,
      account_id: scope === "account" ? accountId ?? null : null,
      category: scope === "category" ? (category ?? null) : null,
    }
    try {
      await createGoal.mutateAsync(payload)
      toast.success(`${name} added`)
      resetForm()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that goal"))
    }
  }

  async function removeGoal(id: number, goalName: string) {
    try {
      await deleteGoal.mutateAsync(id)
      toast.success(`${goalName} removed`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not remove that goal"))
    }
  }

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="What you’re saving towards"
        title="Goals"
        description="Progress uses today’s values; the projected date uses the base scenario."
      />

      {!isLoading && (goals ?? []).length === 0 && (
        <EmptyState
          title="No goals yet"
          description="Set a target for your household, a person, an account or a whole category, and track progress toward it."
        />
      )}

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {(goals ?? []).map((goal) => {
          const pct = Math.max(0, Math.min(1, goal.progress ?? 0))
          return (
            <Card key={goal.id} variant="boxed">
              <CardHeader className="flex flex-row items-start justify-between gap-2">
                <div>
                  <CardTitle>{goal.name}</CardTitle>
                  <p className="text-xs text-ink-muted">
                    {SCOPES.find((s) => s.value === goal.scope)?.label}
                    {goal.category ? ` · ${CATEGORY_LABELS[goal.category as Category]}` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeGoal(goal.id, goal.name)}
                  aria-label={`Delete goal ${goal.name}`}
                >
                  Delete
                </Button>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                <div className="flex flex-wrap items-baseline gap-x-2.5">
                  <Money value={goal.current_value_gbp ?? 0} display whole className="text-4xl text-ink" />
                  <span className="text-sm text-ink-muted">
                    of <Money value={goal.target_gbp} whole />
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-rule-soft" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct * 100)} aria-label={`${goal.name} progress`}>
                  <div
                    className="h-2.5 rounded-full bg-primary"
                    style={{ width: `${pct * 100}%` }}
                  />
                </div>
                <p className="text-xs text-ink-muted">
                  {goal.projected_hit_date
                    ? `Projected to reach target ${formatDate(goal.projected_hit_date)}`
                    : "Not projected to reach target under current assumptions"}
                  {goal.target_date ? ` · Target date ${formatDate(goal.target_date)}` : ""}
                </p>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Add a goal</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="goal-name">Name</Label>
              <Input
                id="goal-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Emergency fund"
                className="w-48"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="goal-target">Target</Label>
              <MoneyInput id="goal-target" value={target} onChange={setTarget} className="w-32" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="goal-date">Target date (optional)</Label>
              <DateInput id="goal-date" value={targetDate} onChange={setTargetDate} className="w-40" />
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="goal-scope">Scope</Label>
              <select
                id="goal-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value as GoalScope)}
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-ink"
              >
                {SCOPES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            {scope === "person" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="goal-person">Person</Label>
                <select
                  id="goal-person"
                  value={personId ?? ""}
                  onChange={(e) => setPersonId(e.target.value ? Number(e.target.value) : undefined)}
                  className="h-9 rounded-md border border-border bg-card px-2 text-sm text-ink"
                >
                  <option value="">Select…</option>
                  {(people ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {scope === "account" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="goal-account">Account</Label>
                <select
                  id="goal-account"
                  value={accountId ?? ""}
                  onChange={(e) => setAccountId(e.target.value ? Number(e.target.value) : undefined)}
                  className="h-9 rounded-md border border-border bg-card px-2 text-sm text-ink"
                >
                  <option value="">Select…</option>
                  {(accounts ?? []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {scope === "category" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="goal-category">Category</Label>
                <select
                  id="goal-category"
                  value={category ?? ""}
                  onChange={(e) => setCategory((e.target.value || undefined) as Category | undefined)}
                  className="h-9 rounded-md border border-border bg-card px-2 text-sm text-ink"
                >
                  <option value="">Select…</option>
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <Button
              onClick={addGoal}
              disabled={
                !name.trim() ||
                !target ||
                createGoal.isPending ||
                (scope === "person" && !personId) ||
                (scope === "account" && !accountId) ||
                (scope === "category" && !category)
              }
            >
              Add goal
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
