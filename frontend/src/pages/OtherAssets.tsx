import { useState } from "react"
import { Link } from "react-router"
import { useAccounts } from "@/api/hooks/useAccounts"
import { AccountFormDialog } from "@/components/AccountFormDialog"
import { CategoryIcon } from "@/components/CategoryIcon"
import { EmptyState } from "@/components/EmptyState"
import { Money } from "@/components/Money"
import { PersonAvatar } from "@/components/PersonAvatar"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/PageHeader"
import { Plus } from "lucide-react"
import { VALUATION_METHOD_LABELS } from "@/lib/categories"
import { formatDate } from "@/lib/dates"

function sum(accounts: { value_gbp: number }[]): number {
  return accounts.reduce((total, a) => total + a.value_gbp, 0)
}

export function OtherAssets() {
  // Cash, loans and credit cards have no page of their own, so they are listed here too.
  const { data: cash } = useAccounts({ category: "cash" })
  const { data: assets } = useAccounts({ category: "other_asset" })
  const { data: otherLiabilities } = useAccounts({ category: "other_liability" })
  const { data: loans } = useAccounts({ category: "loan" })
  const { data: creditCards } = useAccounts({ category: "credit_card" })
  const [addOpen, setAddOpen] = useState(false)

  const liabilities = [...(loans ?? []), ...(creditCards ?? []), ...(otherLiabilities ?? [])]
  const nothingYet = (cash?.length ?? 0) === 0 && (assets?.length ?? 0) === 0 && liabilities.length === 0

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow="Everything else you own and owe"
        title="Other assets"
        actions={
          <Button onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" />
            Add asset
          </Button>
        }
      />

      {nothingYet && (
        <EmptyState
          title="No other assets yet"
          description="Cash savings, cars, watches, jewellery, art, or anything else that appreciates or depreciates."
        />
      )}

      {(cash?.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Cash</CardTitle>
            <CardAction>
              <Money value={sum(cash!)} whole className="font-heading text-[22px] text-ink" />
            </CardAction>
          </CardHeader>
          <CardContent>
            <AccountCards accounts={cash!} category="cash" />
          </CardContent>
        </Card>
      )}

      {(assets?.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Other assets</CardTitle>
            <CardAction>
              <Money value={sum(assets!)} whole className="font-heading text-[22px] text-ink" />
            </CardAction>
          </CardHeader>
          <CardContent>
            <AccountCards accounts={assets!} category="other_asset" />
          </CardContent>
        </Card>
      )}

      {liabilities.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Debts</CardTitle>
            <CardAction>
              <Money value={sum(liabilities)} whole className="font-heading text-[22px] text-ink" />
            </CardAction>
          </CardHeader>
          <CardContent className="flex flex-col">
            {liabilities.map((account) => (
              <Link
                key={account.id}
                to={`/accounts/${account.id}`}
                className="flex min-h-13 items-center gap-3 border-b border-rule-soft py-2 text-sm transition-colors last:border-b-0 hover:bg-muted/60"
              >
                <CategoryIcon category={account.category as "loan"} className="size-4 text-ink-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-ink">{account.name}</p>
                  {account.provider && <p className="truncate text-xs text-ink-muted">{account.provider}</p>}
                </div>
                <div className="flex -space-x-1.5">
                  {account.owners.map((o) => (
                    <PersonAvatar key={o.person_id} name={o.name} color={o.color} size="sm" className="ring-2 ring-background" />
                  ))}
                </div>
                <Money value={account.value_gbp} className="w-28 text-right text-ink" />
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      <AccountFormDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

type AccountSummary = NonNullable<ReturnType<typeof useAccounts>["data"]>[number]

function AccountCards({ accounts, category }: { accounts: AccountSummary[]; category: "cash" | "other_asset" }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {accounts.map((account) => (
        <Link key={account.id} to={`/accounts/${account.id}`} className="group/acct">
          <Card variant="boxed" className="h-full transition-colors group-hover/acct:border-ink-muted">
            <CardContent className="flex flex-col gap-2.5">
              <div className="flex items-center gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                  <CategoryIcon category={category} className="size-5 text-ink-2" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-medium text-ink">{account.name}</p>
                  {account.provider && <p className="truncate text-xs text-ink-muted">{account.provider}</p>}
                </div>
              </div>
              <p className="text-[30px] leading-tight text-ink">
                <Money value={account.value_gbp} display />
              </p>
              <div className="flex items-center justify-between text-xs text-ink-muted">
                <span>{VALUATION_METHOD_LABELS[account.valuation_method]}</span>
                <div className="flex -space-x-1.5">
                  {account.owners.map((o) => (
                    <PersonAvatar key={o.person_id} name={o.name} color={o.color} size="sm" />
                  ))}
                </div>
              </div>
              {account.last_updated && (
                <p className="border-t border-rule-soft pt-2.5 text-xs text-ink-muted">
                  Last valued {formatDate(account.last_updated)}
                </p>
              )}
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  )
}
