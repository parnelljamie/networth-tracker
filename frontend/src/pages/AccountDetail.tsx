import { DbPensionTab } from "@/components/DbPensionTab"
import { ChevronRight, Trash2 } from "lucide-react"
import { Link, useNavigate, useParams } from "react-router"
import { toast } from "sonner"
import { useAccount, useDeleteAccount } from "@/api/hooks/useAccounts"
import { useAccountXirr } from "@/api/hooks/useInsights"
import { DeltaChip } from "@/components/DeltaChip"
import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { PersonAvatar } from "@/components/PersonAvatar"
import { apiErrorMessage } from "@/lib/api-error"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CATEGORY_LABELS, WRAPPER_LABELS, type Category } from "@/lib/categories"
import { PlaceholderPage } from "@/pages/PlaceholderPage"
import { PlansTab } from "@/components/account/PlansTab"
import { BalancesTab } from "@/components/account/BalancesTab"
import { AccountHistoryTab } from "@/components/account/AccountHistoryTab"
import { HoldingsTab } from "@/components/account/HoldingsTab"
import { TransactionsTab } from "@/components/account/TransactionsTab"
import { SettingsTab } from "@/components/account/SettingsTab"
import { formatDate } from "@/lib/dates"

/** Where the breadcrumb's category link goes: the household page that lists this kind of account. */
const CATEGORY_PAGES: Record<string, string> = {
  investment: "/investments",
  pension: "/pensions",
  property: "/property",
  mortgage: "/property",
  cash: "/other",
  other_asset: "/other",
  loan: "/other",
  credit_card: "/other",
  other_liability: "/other",
}

export function AccountDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const accountId = Number(id)
  const { data: account, isLoading } = useAccount(accountId)
  const isHoldings = account?.valuation_method === "holdings"
  const isDefinedBenefit = account?.valuation_method === "defined_benefit"
  const { data: xirr } = useAccountXirr(isHoldings ? accountId : undefined)
  const deleteAccount = useDeleteAccount()

  if (isLoading || !account) return <PlaceholderPage title="Account" note="Loading…" />

  async function remove() {
    if (!account) return
    try {
      await deleteAccount.mutateAsync(account.id)
      toast.success("Account deleted")
      navigate("/")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not delete this account"))
    }
  }

  const categoryLabel = CATEGORY_LABELS[account.category as Category] ?? account.category

  return (
    <div className="flex flex-col gap-8 md:gap-10">
      <header className="flex flex-wrap items-end justify-between gap-x-10 gap-y-5">
        <div className="flex min-w-0 flex-col gap-2.5">
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[13px] text-ink-muted">
            <Link to={CATEGORY_PAGES[account.category] ?? "/"} className="text-ink-2 hover:text-ink">
              {categoryLabel}
            </Link>
            <ChevronRight className="size-3.5" aria-hidden="true" />
            <span className="truncate">{account.provider || account.name}</span>
          </nav>
          <h1 className="page-title text-4xl break-words md:text-5xl">{account.name}</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-2">
            {account.wrapper !== "none" && (
              <span className="rounded border border-brass px-2 py-px text-xs font-semibold tracking-wider text-brass">
                {WRAPPER_LABELS[account.wrapper]}
              </span>
            )}
            {account.is_archived && (
              <span className="rounded border border-border px-2 py-px text-xs text-ink-muted">Archived</span>
            )}
            {account.provider && <span>{account.provider}</span>}
            {account.owners.length > 0 && (
              <span className="flex items-center gap-1.5">
                <span className="flex -space-x-1.5">
                  {account.owners.map((o) => (
                    <PersonAvatar key={o.person_id} name={o.name} color={o.color} size="sm" className="ring-2 ring-background" />
                  ))}
                </span>
                {account.owners.map((o) => o.name).join(" & ")}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
          <div className="flex flex-col items-start gap-1.5 md:items-end">
            <Money value={account.value_gbp} display className="text-5xl leading-none text-ink md:text-[56px]" />
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
              {isHoldings && account.day_change_gbp !== null && account.day_change_gbp !== undefined && (
                <span className="flex items-baseline gap-1.5">
                  <DeltaChip amountGbp={account.day_change_gbp} pct={account.day_change_pct ?? undefined} />
                  <span className="text-ink-muted">today</span>
                </span>
              )}
              {isHoldings && (
                <span className="text-ink-muted">
                  Money-weighted return{" "}
                  {xirr?.xirr !== null && xirr?.xirr !== undefined ? (
                    <span className="text-ink">
                      <Pct value={xirr.xirr} />{" "}
                      {xirr.annualised || !xirr.since ? "a year" : `since ${formatDate(xirr.since)}`}
                    </span>
                  ) : (
                    "n/a"
                  )}
                </span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <AlertDialog>
              <AlertDialogTrigger
                render={
                  <Button variant="outline" disabled={deleteAccount.isPending} />
                }
              >
                <Trash2 aria-hidden="true" />
                Delete
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this account?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This permanently removes the account and all of its history — balances,
                    transactions and snapshots. This can&apos;t be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction variant="destructive" onClick={remove}>
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
        {account.detail && <p className="w-full text-xs text-warn">{account.detail}</p>}
      </header>

      <Tabs defaultValue={isHoldings ? "holdings" : isDefinedBenefit ? "scheme" : "balances"}>
        <TabsList>
          {isDefinedBenefit ? (
            <TabsTrigger value="scheme">Scheme</TabsTrigger>
          ) : isHoldings ? (
            <>
              <TabsTrigger value="holdings">Holdings</TabsTrigger>
              <TabsTrigger value="transactions">Transactions</TabsTrigger>
            </>
          ) : (
            <TabsTrigger value="balances">Balances</TabsTrigger>
          )}
          <TabsTrigger value="history">History</TabsTrigger>
          {!isDefinedBenefit && <TabsTrigger value="plans">Regular Payments</TabsTrigger>}
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        {isDefinedBenefit ? (
          <TabsContent value="scheme" className="mt-6">
            <DbPensionTab account={account} />
          </TabsContent>
        ) : isHoldings ? (
          <>
            <TabsContent value="holdings" className="mt-6">
              <HoldingsTab accountId={account.id} />
            </TabsContent>
            <TabsContent value="transactions" className="mt-6">
              <TransactionsTab accountId={account.id} />
            </TabsContent>
          </>
        ) : (
          <TabsContent value="balances" className="mt-6">
            <BalancesTab accountId={account.id} />
          </TabsContent>
        )}

        <TabsContent value="history" className="mt-6">
          <AccountHistoryTab accountId={account.id} isHoldings={isHoldings} />
        </TabsContent>

        <TabsContent value="plans" className="mt-6">
          <PlansTab
            accountId={account.id}
            isHoldings={isHoldings}
            isLoan={account.valuation_method === "amortising"}
            brokerSynced={account.broker_sync != null}
          />
        </TabsContent>

        <TabsContent value="settings" className="mt-6">
          <SettingsTab account={account} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
