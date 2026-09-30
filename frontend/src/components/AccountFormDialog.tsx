import { addYears, format } from "date-fns"
import { DbPensionFields } from "@/components/DbPensionFields"
import { detailsFromDraft, emptyDbPensionDraft } from "@/lib/dbPension"
import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"
import type { AccountCreate } from "@/api/hooks/useAccounts"
import { useCreateAccount } from "@/api/hooks/useAccounts"
import { usePeople } from "@/api/hooks/usePeople"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CategoryIcon } from "@/components/CategoryIcon"
import { DateInput } from "@/components/DateInput"
import { MoneyInput } from "@/components/MoneyInput"
import { OwnersEditor, type OwnerShareValue } from "@/components/OwnersEditor"
import { PercentInput } from "@/components/PercentInput"
import { apiErrorMessage } from "@/lib/api-error"
import {
  ALLOWED_WRAPPERS,
  CATEGORY_LABELS,
  VALUATION_METHOD_LABELS,
  WRAPPER_LABELS,
  methodsForWrapper,
  type Category,
} from "@/lib/categories"
import { todayIso } from "@/lib/dates"
import { cn } from "@/lib/utils"

const CATEGORIES = Object.keys(CATEGORY_LABELS) as Category[]
const SINGLE_OWNER_WRAPPERS = new Set(["isa", "lisa", "jisa", "sipp", "workplace_pension", "db_pension"])

const STEPS = ["category", "wrapper", "owners", "method", "details"] as const
type Step = (typeof STEPS)[number]

interface AccountFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Pre-select a category/wrapper (e.g. Overview's empty-state "Add your ISA" action). */
  defaultCategory?: Category
  defaultWrapper?: string
  /**
   * Pre-select the valuation method too and jump straight to the "details" step, skipping
   * category/wrapper/owners/method entirely (e.g. Property page's "Add mortgage" action).
   */
  defaultMethod?: string
  /** Pre-fill owners (e.g. match the linked property's owners) when the owners step is skipped. */
  defaultOwners?: OwnerShareValue[]
  /** Link the created loan to this property account (`loan.secured_on_account_id`). */
  securedOnAccountId?: number
  /**
   * Simplify the amortising "details" fields to just mortgage value, start date, term (years)
   * and interest rate — used by the property "Add mortgage" flow. The fallback rate is set to
   * match the entered rate and the maturity date is derived from start date + term.
   */
  quickMortgage?: boolean
  /** Override the dialog title (defaults to "Add account"). */
  dialogTitle?: string
  /**
   * Called after a successful create instead of the default behaviour of navigating to the new
   * account. Use this when staying on the current page makes more sense (e.g. the property page
   * already shows the newly-linked mortgage immediately).
   */
  onCreated?: (account: { id: number }) => void
}

function initialState(
  defaultCategory?: Category,
  defaultWrapper?: string,
  defaultMethod?: string,
  defaultOwners?: OwnerShareValue[]
) {
  return {
    category: defaultCategory,
    wrapper: defaultWrapper,
    owners: defaultOwners ?? ([] as OwnerShareValue[]),
    method: defaultMethod,
    name: "",
    provider: "",
    initialDate: todayIso(),
    initialBalance: undefined as number | undefined,
    growthRate: undefined as number | undefined,
    address: "",
    purchaseDate: undefined as string | undefined,
    purchasePrice: undefined as number | undefined,
    lender: "",
    originalAmount: undefined as number | undefined,
    loanStartDate: todayIso(),
    maturityDate: undefined as string | undefined,
    termYears: undefined as number | undefined,
    fallbackRate: undefined as number | undefined,
    initialRate: undefined as number | undefined,
    dbPension: emptyDbPensionDraft(),
  }
}

export function AccountFormDialog({
  open,
  onOpenChange,
  defaultCategory,
  defaultWrapper,
  defaultMethod,
  defaultOwners,
  securedOnAccountId,
  quickMortgage,
  dialogTitle,
  onCreated,
}: AccountFormDialogProps) {
  const { data: people } = usePeople()
  const createAccount = useCreateAccount()
  const navigate = useNavigate()
  // When a default category+wrapper+method are all given (e.g. Property's "Add mortgage"), skip
  // straight to "details". With just category+wrapper (e.g. Overview's "Add your ISA"), skip the
  // category and wrapper picker steps and land on "owners". With just a category (e.g. Pensions'
  // "Add pension"), start at the wrapper picker.
  const initialStepIndex =
    defaultCategory && defaultWrapper && defaultMethod
      ? STEPS.indexOf("details")
      : defaultCategory && defaultWrapper
        ? STEPS.indexOf("owners")
        : defaultCategory
          ? STEPS.indexOf("wrapper")
          : 0
  const [stepIndex, setStepIndex] = useState(initialStepIndex)
  const [form, setForm] = useState(
    initialState(defaultCategory, defaultWrapper, defaultMethod, defaultOwners)
  )

  const step: Step = STEPS[stepIndex]

  const reset = useCallback(() => {
    setStepIndex(initialStepIndex)
    setForm(initialState(defaultCategory, defaultWrapper, defaultMethod, defaultOwners))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialStepIndex, defaultCategory, defaultWrapper, defaultMethod, defaultOwners])

  // Re-initialize whenever the dialog opens, so a fresh defaultCategory/defaultWrapper (e.g.
  // Overview's "Add your ISA" vs. a plain "Add account") isn't stuck from a previous session —
  // useState's initial value only runs once on mount, this component stays mounted across opens.
  // Deliberately keyed on `open` alone: `reset` can change identity while the dialog stays open
  // (e.g. Property's `defaultOwners` array is a fresh literal each render) and re-running it then
  // would wipe whatever the user has typed.
  useEffect(() => {
    if (open) reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function close() {
    onOpenChange(false)
    reset()
  }

  // A step is only worth showing when the current selections leave more than one valid
  // option — e.g. a mortgage only ever has wrapper "none", so don't make the user click
  // through a picker with a single, obvious button. Auto-resolve those steps instead.
  const isStepVisible = useCallback((s: Step, f: typeof form) => {
    if (s === "wrapper") {
      return (f.category ? ALLOWED_WRAPPERS[f.category] : []).length > 1
    }
    if (s === "method") {
      return (f.category ? methodsForWrapper(f.category, f.wrapper ?? "none") : []).length > 1
    }
    return true
  }, [])

  function goNext() {
    setStepIndex((i) => {
      let next = i + 1
      while (next < STEPS.length - 1 && !isStepVisible(STEPS[next], form)) next++
      return Math.min(next, STEPS.length - 1)
    })
  }
  function goBack() {
    setStepIndex((i) => {
      let prev = i - 1
      while (prev > 0 && !isStepVisible(STEPS[prev], form)) prev--
      return Math.max(prev, 0)
    })
  }

  const wrapperOptions = form.category ? ALLOWED_WRAPPERS[form.category] : []
  const methodOptions = form.category ? methodsForWrapper(form.category, form.wrapper ?? "none") : []
  const visibleSteps = STEPS.filter((s) => isStepVisible(s, form))
  const visibleStepIndex = visibleSteps.indexOf(step)
  const singleOwner = form.wrapper ? SINGLE_OWNER_WRAPPERS.has(form.wrapper) : false
  const ownersShareTotal = form.owners.reduce((sum, o) => sum + o.share, 0)

  const canProceed: Record<Step, boolean> = {
    category: form.category !== undefined,
    wrapper: form.wrapper !== undefined,
    owners:
      form.owners.length > 0 && (singleOwner ? true : Math.abs(ownersShareTotal - 1) < 1e-6),
    method: form.method !== undefined,
    details:
      form.name.trim().length > 0 &&
      (form.category !== "property" || form.address.trim().length > 0) &&
      (form.method !== "defined_benefit" || detailsFromDraft(form.dbPension) !== null) &&
      (form.method !== "amortising" ||
        (quickMortgage
          ? form.originalAmount !== undefined &&
            form.termYears !== undefined &&
            form.termYears > 0 &&
            form.initialRate !== undefined
          : form.maturityDate !== undefined && form.fallbackRate !== undefined)),
  }

  // quickMortgage asks for term-in-years + one rate rather than a maturity date + fallback rate;
  // derive the fields the backend actually stores.
  const derivedMaturityDate =
    quickMortgage && form.termYears !== undefined
      ? format(addYears(new Date(form.loanStartDate), form.termYears), "yyyy-MM-dd")
      : form.maturityDate
  const derivedFallbackRate = quickMortgage ? form.initialRate : form.fallbackRate

  async function submit() {
    if (!form.category || !form.wrapper || !form.method) return
    const payload: AccountCreate = {
      name: form.name,
      category: form.category,
      wrapper: form.wrapper as AccountCreate["wrapper"],
      valuation_method: form.method as AccountCreate["valuation_method"],
      provider: form.provider || null,
      owners: form.owners.map((o) => ({ person_id: o.personId, share: o.share })),
      initial_balance:
        form.method !== "holdings" &&
        form.method !== "amortising" &&
        form.method !== "defined_benefit" &&
        form.initialBalance !== undefined
          ? { date: form.initialDate, balance_gbp: form.initialBalance }
          : undefined,
      growth_model:
        form.method === "model" && form.growthRate !== undefined
          ? { annual_rate: form.growthRate, method: "compound" }
          : undefined,
      property:
        form.category === "property"
          ? {
              address: form.address,
              purchase_date: form.purchaseDate,
              purchase_price_gbp: form.purchasePrice,
              is_main_residence: true,
            }
          : undefined,
      db_pension: form.method === "defined_benefit" ? detailsFromDraft(form.dbPension) : undefined,
      loan:
        form.method === "amortising" && derivedMaturityDate && derivedFallbackRate !== undefined
          ? {
              secured_on_account_id: securedOnAccountId ?? null,
              lender: form.lender || null,
              original_amount_gbp: form.originalAmount,
              start_date: form.loanStartDate,
              maturity_date: derivedMaturityDate,
              fallback_rate: derivedFallbackRate,
              rate_periods:
                form.initialRate !== undefined
                  ? [
                      {
                        start_date: form.loanStartDate,
                        end_date: null,
                        annual_rate: form.initialRate,
                        rate_type: "fixed",
                      },
                    ]
                  : [],
            }
          : undefined,
    }

    try {
      const created = await createAccount.mutateAsync(payload)
      toast.success(`${form.name} added`)
      close()
      if (onCreated) {
        if (created) onCreated(created)
      } else if (created) {
        // Generic top-bar/Overview "Add account" flow: the dialog is reachable from every page,
        // so navigate to the new account or it looks like it silently vanished (the dialog would
        // otherwise close with no on-screen change on pages with no accounts list).
        navigate(`/accounts/${created.id}`)
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not create the account — check the details and try again"))
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close()
        else onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{dialogTitle ?? "Add account"}</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-1.5 pb-2">
          {visibleSteps.map((s, i) => (
            <span
              key={s}
              className={cn(
                "h-1 flex-1 rounded-full",
                i <= visibleStepIndex ? "bg-primary" : "bg-muted"
              )}
            />
          ))}
        </div>

        {step === "category" && (
          <div className="grid grid-cols-3 gap-2">
            {CATEGORIES.map((category) => (
              <button
                key={category}
                type="button"
                onClick={() => {
                  const wrapperOpts = ALLOWED_WRAPPERS[category]
                  const wrapper = wrapperOpts.length === 1 ? wrapperOpts[0] : undefined
                  const methodOpts = wrapper ? methodsForWrapper(category, wrapper) : []
                  const method = wrapper && methodOpts.length === 1 ? methodOpts[0] : undefined
                  setForm((f) => ({ ...f, category, wrapper, method }))
                }}
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-lg border p-3 text-xs",
                  form.category === category
                    ? "border-primary bg-muted text-ink"
                    : "border-border text-ink-2 hover:bg-muted"
                )}
              >
                <CategoryIcon category={category} className="size-5" />
                {CATEGORY_LABELS[category]}
              </button>
            ))}
          </div>
        )}

        {step === "wrapper" && form.category && (
          <div className="flex flex-col gap-2">
            {wrapperOptions.map((wrapper) => (
              <button
                key={wrapper}
                type="button"
                onClick={() => {
                  const methodOpts = form.category ? methodsForWrapper(form.category, wrapper) : []
                  const method = methodOpts.length === 1 ? methodOpts[0] : undefined
                  setForm((f) => ({ ...f, wrapper, method }))
                }}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left text-sm",
                  form.wrapper === wrapper
                    ? "border-primary bg-muted text-ink"
                    : "border-border text-ink-2 hover:bg-muted"
                )}
              >
                {WRAPPER_LABELS[wrapper]}
              </button>
            ))}
          </div>
        )}

        {step === "owners" && (
          <OwnersEditor
            people={people ?? []}
            value={form.owners}
            onChange={(owners) => setForm((f) => ({ ...f, owners }))}
            singleOwner={singleOwner}
          />
        )}

        {step === "method" && (
          <div className="flex flex-col gap-2">
            {methodOptions.map((method) => (
              <button
                key={method}
                type="button"
                onClick={() => setForm((f) => ({ ...f, method }))}
                className={cn(
                  "rounded-lg border px-3 py-2 text-left text-sm",
                  form.method === method
                    ? "border-primary bg-muted text-ink"
                    : "border-border text-ink-2 hover:bg-muted"
                )}
              >
                {VALUATION_METHOD_LABELS[method]}
              </button>
            ))}
          </div>
        )}

        {step === "details" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="account-name">Name</Label>
              <Input
                id="account-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Trading 212 S&S ISA"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="account-provider">Provider</Label>
              <Input
                id="account-provider"
                value={form.provider}
                onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
                placeholder="e.g. Trading 212"
              />
            </div>

            {form.category === "property" && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="property-address">Address</Label>
                  <Input
                    id="property-address"
                    value={form.address}
                    onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Purchase date</Label>
                    <DateInput
                      value={form.purchaseDate}
                      onChange={(v) => setForm((f) => ({ ...f, purchaseDate: v }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Purchase price</Label>
                    <MoneyInput
                      value={form.purchasePrice}
                      onChange={(v) => setForm((f) => ({ ...f, purchasePrice: v }))}
                    />
                  </div>
                </div>
              </>
            )}

            {form.method === "holdings" ? (
              <p className="text-sm text-ink-muted">
                Add holdings and cash on the account page once it's created.
              </p>
            ) : form.method === "defined_benefit" ? (
              <DbPensionFields
                value={form.dbPension}
                onChange={(dbPension) => setForm((f) => ({ ...f, dbPension }))}
              />
            ) : form.method === "amortising" && quickMortgage ? (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Mortgage value</Label>
                    <MoneyInput
                      value={form.originalAmount}
                      onChange={(v) => setForm((f) => ({ ...f, originalAmount: v }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Start date</Label>
                    <DateInput
                      value={form.loanStartDate}
                      onChange={(v) => setForm((f) => ({ ...f, loanStartDate: v ?? todayIso() }))}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Term (years)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={form.termYears ?? ""}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          termYears: e.target.value === "" ? undefined : Number(e.target.value),
                        }))
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Interest rate</Label>
                    <PercentInput
                      value={form.initialRate}
                      onChange={(v) => setForm((f) => ({ ...f, initialRate: v }))}
                    />
                  </div>
                </div>
                {derivedMaturityDate && (
                  <p className="text-xs text-ink-muted">
                    Maturity date: {derivedMaturityDate}
                  </p>
                )}
                <p className="text-xs text-ink-muted">
                  Lender, individual rate periods and overpayments can be added from the Property
                  &amp; Mortgage page once it's created.
                </p>
              </div>
            ) : form.method === "amortising" ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Lender</Label>
                  <Input
                    value={form.lender}
                    onChange={(e) => setForm((f) => ({ ...f, lender: e.target.value }))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Original amount</Label>
                    <MoneyInput
                      value={form.originalAmount}
                      onChange={(v) => setForm((f) => ({ ...f, originalAmount: v }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Start date</Label>
                    <DateInput
                      value={form.loanStartDate}
                      onChange={(v) => setForm((f) => ({ ...f, loanStartDate: v ?? todayIso() }))}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>Maturity date</Label>
                    <DateInput
                      value={form.maturityDate}
                      onChange={(v) => setForm((f) => ({ ...f, maturityDate: v }))}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>Fallback rate</Label>
                    <PercentInput
                      value={form.fallbackRate}
                      onChange={(v) => setForm((f) => ({ ...f, fallbackRate: v }))}
                    />
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>Current rate (optional initial rate period)</Label>
                  <PercentInput
                    value={form.initialRate}
                    onChange={(v) => setForm((f) => ({ ...f, initialRate: v }))}
                  />
                </div>
                <p className="text-xs text-ink-muted">
                  Add a statement balance, more rate periods and overpayments on the Property &amp;
                  Mortgage page once it's created.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label>Value date</Label>
                  <DateInput
                    value={form.initialDate}
                    onChange={(v) => setForm((f) => ({ ...f, initialDate: v ?? todayIso() }))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label>{form.category === "property" ? "Current value" : "Initial value"}</Label>
                  <MoneyInput
                    value={form.initialBalance}
                    onChange={(v) => setForm((f) => ({ ...f, initialBalance: v }))}
                  />
                </div>
              </div>
            )}

            {form.method === "model" && (
              <div className="flex flex-col gap-1.5">
                <Label>Annual growth rate (negative to depreciate)</Label>
                <PercentInput
                  value={form.growthRate}
                  onChange={(v) => setForm((f) => ({ ...f, growthRate: v }))}
                />
              </div>
            )}
          </div>
        )}

        <DialogFooter className="mt-2">
          {stepIndex > 0 && (
            <Button type="button" variant="outline" onClick={goBack}>
              Back
            </Button>
          )}
          {step !== "details" ? (
            <Button type="button" onClick={goNext} disabled={!canProceed[step]}>
              Next
            </Button>
          ) : (
            <Button
              type="button"
              onClick={submit}
              disabled={!canProceed.details || createAccount.isPending}
            >
              Create account
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
