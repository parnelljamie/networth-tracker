import { Pencil, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router"
import { toast } from "sonner"
import { useAccounts, useDeleteAccount, type AccountSummary } from "@/api/hooks/useAccounts"
import { useNetWorthCurrent } from "@/api/hooks/useNetworth"
import { usePeople } from "@/api/hooks/usePeople"
import { AccountEditDialog } from "@/components/AccountEditDialog"
import { AllowanceMeters } from "@/components/AllowanceMeters"
import { DeltaChip } from "@/components/DeltaChip"
import { PageHeader } from "@/components/PageHeader"
import { Money } from "@/components/Money"
import { Pct } from "@/components/Pct"
import { PersonAvatar } from "@/components/PersonAvatar"
import { StalenessBadge } from "@/components/StalenessBadge"
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
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAllowances } from "@/api/hooks/useRecurring"
import { openAddAccount } from "@/lib/appDialogs"
import { CATEGORY_COLORS, CATEGORY_GROUP_ORDER, CATEGORY_LABELS, type Category } from "@/lib/categories"
import { useTheme } from "@/lib/theme"
import { PlaceholderPage } from "./PlaceholderPage"

function ageInYears(dob: string): number {
  const birth = new Date(`${dob}T00:00:00`)
  const now = new Date()
  let age = now.getFullYear() - birth.getFullYear()
  if (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())) age -= 1
  return age
}

export function Person() {
  const { id } = useParams()
  const personId = Number(id)
  const { data: people } = usePeople()
  const { data: networth } = useNetWorthCurrent(personId)
  // Archived accounts are included so the "All accounts" list below can still reach (and delete)
  // them — archiving is no longer offered in the UI, so an unlisted archived account would be
  // invisible and undeletable. The stat tiles below filter them back out, because archived
  // accounts are excluded from the net worth figure in the header.
  const { data: allAccounts } = useAccounts({ personId, includeArchived: true })

  const { data: allowances } = useAllowances()
  const personAllowances = (allowances ?? []).filter((a) => a.person_id === personId)
  const theme = useTheme()
  const person = people?.find((p) => p.id === personId)
  if (!person) return <PlaceholderPage title="Person" note="Loading…" />

  const byCategory = new Map<string, number>()
  for (const account of allAccounts ?? []) {
    if (account.is_archived) continue
    byCategory.set(account.category, (byCategory.get(account.category) ?? 0) + account.scoped_value_gbp)
  }

  const age = person.date_of_birth ? ageInYears(person.date_of_birth) : null
  const kicker = ["Person", age !== null ? `age ${age}` : null, `retires at ${person.retirement_age}`]
    .filter(Boolean)
    .join(" · ")
  const day = networth?.changes.day

  return (
    <div className="flex flex-col gap-10 md:gap-12">
      <PageHeader
        eyebrow={kicker}
        title={person.name}
        leading={<PersonAvatar name={person.name} color={person.color} className="size-16 text-2xl [&_span]:text-2xl" />}
        actions={
          <div className="flex flex-col items-start gap-1.5 md:items-end">
            <Money value={networth?.total_gbp ?? 0} display whole className="text-5xl leading-none text-ink md:text-[56px]" />
            {day && day.abs_gbp !== null && day.abs_gbp !== undefined && (
              <span className="flex items-baseline gap-2 text-sm">
                <DeltaChip amountGbp={day.abs_gbp} pct={day.pct ?? undefined} />
                <span className="text-ink-muted">today</span>
              </span>
            )}
          </div>
        }
      />

      <section className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-7 gap-y-6" aria-label="By category">
        {CATEGORY_GROUP_ORDER.filter((c) => byCategory.has(c)).map((category) => [category, byCategory.get(category) ?? 0] as const).map(([category, value]) => (
          <div
            key={category}
            className="flex min-w-0 flex-col gap-1.5 border-t-[3px] pt-2.5"
            style={{ borderColor: CATEGORY_COLORS[category as Category]?.[theme] ?? "var(--border)" }}
          >
            <span className="text-[13px] text-ink-2">{CATEGORY_LABELS[category as Category] ?? category}</span>
            <Money value={value} whole className="font-heading text-[28px] leading-tight text-ink" />
            {networth?.total_gbp ? (
              <span className="text-xs text-ink-muted">
                <Pct value={Math.abs(value) / networth.total_gbp} decimals={0} /> of {person.name}’s total
              </span>
            ) : null}
          </div>
        ))}
        {byCategory.size === 0 && <p className="text-sm text-ink-muted">No accounts yet.</p>}
      </section>

      <div className="grid grid-cols-1 gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <PersonAccountsSection accounts={allAccounts ?? []} personName={person.name} />
        <Card>
          <CardHeader>
            <CardTitle>Allowances</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <AllowanceMeters allowances={personAllowances} kind="isa" showRemaining emptyNote="No ISA allowance this tax year." />
            <AllowanceMeters allowances={personAllowances} kind="pension" showRemaining emptyNote="No pension allowance data." />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/**
 * Every account belonging to this person, grouped by category (same order/labels as Overview's
 * Accounts card, docs/05-ui.md), with Edit / Delete reachable in one click — the fast path for
 * managing accounts without navigating to each account page in turn.
 */
function PersonAccountsSection({ accounts, personName }: { accounts: AccountSummary[]; personName: string }) {
  const theme = useTheme()
  const [editingAccountId, setEditingAccountId] = useState<number | undefined>(undefined)

  const byCategory = new Map<string, AccountSummary[]>()
  for (const account of accounts) {
    const list = byCategory.get(account.category) ?? []
    list.push(account)
    byCategory.set(account.category, list)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>All accounts</CardTitle>
        <CardAction>
          <button type="button" className="text-[13px] font-medium text-primary hover:underline" onClick={() => openAddAccount()}>
            Add account for {personName}
          </button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {CATEGORY_GROUP_ORDER.filter((c) => byCategory.has(c)).map((category) => {
          const rows = byCategory.get(category) ?? []
          return (
            <div key={category}>
              <div className="flex items-center gap-2.5 border-b border-border pt-4 pb-2">
                <span
                  className="size-2 shrink-0 rounded-[2px]"
                  style={{ backgroundColor: CATEGORY_COLORS[category]?.[theme] ?? "var(--ink-muted)" }}
                  aria-hidden="true"
                />
                <span className="font-heading text-[19px] text-ink italic">{CATEGORY_LABELS[category]}</span>
              </div>
              <div className="divide-y divide-rule-soft">
                {rows.map((account) => (
                  <PersonAccountRow
                    key={account.id}
                    account={account}
                    onEdit={() => setEditingAccountId(account.id)}
                  />
                ))}
              </div>
            </div>
          )
        })}
        {accounts.length === 0 && <p className="py-4 text-sm text-ink-muted">No accounts yet.</p>}
      </CardContent>

      <AccountEditDialog
        accountId={editingAccountId}
        open={editingAccountId !== undefined}
        onOpenChange={(open) => !open && setEditingAccountId(undefined)}
      />
    </Card>
  )
}

function PersonAccountRow({ account, onEdit }: { account: AccountSummary; onEdit: () => void }) {
  const deleteAccount = useDeleteAccount()

  async function remove() {
    try {
      await deleteAccount.mutateAsync(account.id)
      toast.success("Account deleted")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not delete this account"))
    }
  }

  return (
    <div className="flex min-h-13 flex-wrap items-center gap-2 py-2 pl-4 text-sm sm:flex-nowrap sm:gap-3">
      <Link to={`/accounts/${account.id}`} className="min-w-0 flex-1 hover:underline">
        <p className="truncate text-ink">{account.name}</p>
        {account.provider && <p className="truncate text-xs text-ink-muted">{account.provider}</p>}
      </Link>
      {account.is_archived && (
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-ink-muted">Archived</span>
      )}
      <div className="flex shrink-0 -space-x-1.5">
        {account.owners.map((o) => (
          <PersonAvatar key={o.person_id} name={o.name} color={o.color} size="sm" />
        ))}
      </div>
      <Money value={account.scoped_value_gbp} className="w-24 shrink-0 text-right text-ink" />
      <StalenessBadge
        staleness={account.staleness as "ok" | "warn" | "alert"}
        daysSince={account.days_since_update ?? null}
        prices={account.valuation_method === "holdings"}
        className="hidden shrink-0 sm:flex"
      />
      <div className="flex shrink-0 items-center gap-0.5">
        <Button size="icon-sm" variant="ghost" title="Edit account" onClick={onEdit}>
          <Pencil className="size-3.5" aria-hidden="true" />
          <span className="sr-only">Edit {account.name}</span>
        </Button>
        <AlertDialog>
          <AlertDialogTrigger
            render={
              <Button
                size="icon-sm"
                variant="ghost"
                className="text-ink-muted hover:text-loss"
                disabled={deleteAccount.isPending}
                title="Delete account"
              />
            }
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
            <span className="sr-only">Delete {account.name}</span>
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
  )
}
