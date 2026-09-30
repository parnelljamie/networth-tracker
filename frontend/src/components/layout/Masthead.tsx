import { Bell, ChevronDown, Eye, EyeOff, Menu, Moon, NotebookPen, Plus, RefreshCw, Search, Sun } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link, NavLink, useLocation } from "react-router"
import { toast } from "sonner"
import { usePricesStatus, useRefreshPrices } from "@/api/hooks/useInstruments"
import { useNetWorthCurrent } from "@/api/hooks/useNetworth"
import { usePeople } from "@/api/hooks/usePeople"
import { useRole } from "@/api/hooks/useSync"
import { useConfirmTransactions, usePendingTransactions } from "@/api/hooks/useTransactions"
import { AccountFormDialog } from "@/components/AccountFormDialog"
import { Money } from "@/components/Money"
import { PersonAvatar } from "@/components/PersonAvatar"
import { QuickUpdateSheet } from "@/components/QuickUpdateSheet"
import { Button } from "@/components/ui/button"
import { apiErrorMessage } from "@/lib/api-error"
import { openAddAccount, setAddAccountOpen, setQuickUpdateOpen, useDialogsState } from "@/lib/appDialogs"
import { openCommandPalette } from "@/lib/commandPalette"
import { daysAgoLabel, formatDate } from "@/lib/dates"
import { togglePrivacyMode, usePrivacyMode } from "@/lib/privacy"
import { toggleTheme, useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { HealthDot } from "./HealthDot"
import { COLUMN, SECTION_LINKS, TOOL_LINKS } from "./nav"

/** A light-dismiss popover anchored under its trigger (bell, People menu). */
function Popover({
  open,
  onClose,
  align = "right",
  className,
  children,
}: {
  open: boolean
  onClose: () => void
  align?: "left" | "right"
  className?: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <>
      <button type="button" aria-label="Close" className="fixed inset-0 z-40 cursor-default" onClick={onClose} />
      <div
        className={cn(
          "absolute top-full z-50 mt-2 rounded-lg border border-border bg-card p-2 shadow-lg",
          align === "right" ? "right-0" : "left-0",
          className
        )}
      >
        {children}
      </div>
    </>
  )
}

function IconButton({
  label,
  onClick,
  children,
  className,
  disabled,
  expanded,
}: {
  label: string
  onClick: () => void
  children: ReactNode
  className?: string
  disabled?: boolean
  expanded?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-expanded={expanded}
      title={label}
      className={cn(
        "relative flex size-10 shrink-0 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-muted hover:text-ink disabled:opacity-50",
        className
      )}
    >
      {children}
    </button>
  )
}

function PendingBell() {
  const [open, setOpen] = useState(false)
  const { data: pending } = usePendingTransactions()
  const confirm = useConfirmTransactions()
  const count = pending?.length ?? 0

  async function confirmOne(id: number) {
    try {
      await confirm.mutateAsync([{ id }])
      toast.success("Confirmed")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not confirm that transaction"))
    }
  }

  async function confirmAll() {
    if (!pending || pending.length === 0) return
    try {
      await confirm.mutateAsync(pending.map((t) => ({ id: t.id })))
      toast.success("All confirmed")
      setOpen(false)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not confirm those transactions"))
    }
  }

  return (
    <div className="relative">
      <IconButton
        label={count > 0 ? `${count} pending confirmation${count === 1 ? "" : "s"}` : "Pending confirmations"}
        onClick={() => setOpen((v) => !v)}
        expanded={open}
      >
        <Bell className="size-[18px]" aria-hidden="true" />
        {count > 0 && (
          <span className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-primary-foreground">
            {count}
          </span>
        )}
      </IconButton>
      <Popover open={open} onClose={() => setOpen(false)} className="w-[min(20rem,calc(100vw-2rem))]">
        <div className="flex items-center justify-between px-1 py-1">
          <p className="text-xs font-medium text-ink-muted">Pending confirmations</p>
          {count > 0 && (
            <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={confirmAll}>
              Confirm all
            </button>
          )}
        </div>
        <div className="flex max-h-80 flex-col divide-y divide-border overflow-y-auto">
          {(pending ?? []).map((txn) => (
            <div key={txn.id} className="flex items-center gap-2 px-1 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate text-ink">
                  {txn.type} · {formatDate(txn.date)}
                </p>
                <Money value={txn.amount_gbp} className="text-xs text-ink-muted" />
              </div>
              <Button size="sm" variant="outline" onClick={() => confirmOne(txn.id)}>
                Confirm
              </Button>
            </div>
          ))}
          {count === 0 && <p className="px-1 py-3 text-sm text-ink-muted">Nothing pending.</p>}
        </div>
      </Popover>
    </div>
  )
}

function lastRefreshLabel(lastRefreshAt: string | null | undefined): string {
  if (!lastRefreshAt) return "Prices not refreshed yet"
  const minutesAgo = Math.max(0, Math.round((Date.now() - new Date(lastRefreshAt).getTime()) / 60_000))
  if (minutesAgo < 1) return "Updated just now"
  if (minutesAgo < 60) return `Updated ${minutesAgo}m ago`
  return `Updated ${daysAgoLabel(Math.floor(minutesAgo / (60 * 24)))}`
}

function useRefreshAction() {
  const { data: status } = usePricesStatus()
  const refreshPrices = useRefreshPrices()

  async function refresh() {
    try {
      const result = await refreshPrices.mutateAsync(true)
      if (result.status === "already_running") {
        toast.info("A price refresh is already running")
      } else if (result.failed.length > 0) {
        toast.warning(`Refreshed ${result.refreshed}, ${result.failed.length} failed`)
      } else {
        toast.success(`Prices refreshed (${result.refreshed})`)
      }
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not refresh prices"))
    }
  }

  return { refresh, pending: refreshPrices.isPending, title: `Refresh prices (${lastRefreshLabel(status?.last_refresh_at)})` }
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "-mb-px inline-flex items-center gap-1 border-b-2 py-3 text-sm whitespace-nowrap transition-colors",
    isActive ? "border-ink font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"
  )

const toolLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "-mb-px border-b-2 py-3 text-[13px] whitespace-nowrap transition-colors",
    isActive ? "border-ink font-semibold text-ink" : "border-transparent text-ink-muted hover:text-ink"
  )

function PeopleMenu() {
  const [open, setOpen] = useState(false)
  const { data: people } = usePeople()
  const { pathname } = useLocation()
  const active = pathname.startsWith("/people/")

  if (!people || people.length === 0) return null
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={navLinkClass({ isActive: active })}
      >
        People
        <ChevronDown className="size-3.5" aria-hidden="true" />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} align="left" className="w-56">
        <ul role="menu" className="flex flex-col">
          {people.map((person) => (
            <li key={person.id} role="none">
              <NavLink
                role="menuitem"
                to={`/people/${person.id}`}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-10 items-center gap-2.5 rounded-md px-2 text-sm hover:bg-muted",
                    isActive ? "font-semibold text-ink" : "text-ink-2"
                  )
                }
              >
                <PersonAvatar name={person.name} color={person.color} />
                {person.name}
              </NavLink>
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
}

export function Wordmark({ className, onClick }: { className?: string; onClick?: () => void }) {
  return (
    <Link to="/" onClick={onClick} className={cn("flex items-baseline gap-2 text-ink", className)} aria-label="Waymark, overview">
      <svg viewBox="8 6 16 21" className="h-[20px] w-auto shrink-0" aria-hidden="true">
        <path d="M9 27V13a7 7 0 0 1 14 0v14z" fill="var(--brass)" />
        <path
          d="M12.4 19.2 16 15.6l3.6 3.6"
          fill="none"
          stroke="var(--page)"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-heading text-[26px] leading-none font-semibold tracking-[-0.02em]">Waymark</span>
    </Link>
  )
}

/**
 * docs/05-ui.md "App shell": a two-row masthead. The top row carries the brand, the household
 * figure and every global action; the second row is the section navigation. Phones get a
 * compact bar and the same navigation in a drawer (`NavDrawer`).
 */
export function Masthead({ onOpenNav }: { onOpenNav: () => void }) {
  const { addAccountOpen, addAccountDefaults, quickUpdateOpen } = useDialogsState()
  const { data: networth } = useNetWorthCurrent()
  const privacy = usePrivacyMode()
  const theme = useTheme()
  const role = useRole()
  const refresh = useRefreshAction()
  // Imports belong on the PC: the phone's copy is replaced at every sync.
  const tools = role === "phone" ? TOOL_LINKS.filter((l) => l.to !== "/import") : TOOL_LINKS

  return (
    <header className="sticky top-0 z-30 shrink-0 border-b border-border bg-background md:static">
      {/* Phones */}
      <div className="flex h-14 items-center gap-1 px-1.5 md:hidden">
        <IconButton label="Open navigation" onClick={onOpenNav}>
          <Menu className="size-5" aria-hidden="true" />
        </IconButton>
        <Wordmark className="min-w-0 flex-1 [&>span:last-child]:text-[22px] [&>svg]:h-[17px]" />
        <IconButton label={refresh.title} onClick={() => void refresh.refresh()} disabled={refresh.pending}>
          <RefreshCw className={cn("size-[18px]", refresh.pending && "animate-spin")} aria-hidden="true" />
        </IconButton>
        <IconButton label="Quick update" onClick={() => setQuickUpdateOpen(true)}>
          <NotebookPen className="size-[18px]" aria-hidden="true" />
        </IconButton>
        <PendingBell />
      </div>

      {/* Desktop */}
      <div className={cn(COLUMN, "hidden md:block")}>
        <div className="flex h-16 items-center gap-2 lg:gap-3">
          <Wordmark />
          <span className="ml-3 hidden items-baseline gap-2 border-l border-border pl-4 text-[13px] text-ink-muted lg:flex">
            Household
            <Money value={networth?.total_gbp ?? 0} display whole className="text-[17px] text-ink" />
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={openCommandPalette}
            className="flex h-10 items-center gap-2.5 rounded-md border border-border bg-card px-3 text-[13px] whitespace-nowrap text-ink-muted transition-colors hover:text-ink xl:w-64"
            title="Search and commands (Ctrl K)"
            aria-label="Search and commands"
          >
            <Search className="size-4 text-ink-2" aria-hidden="true" />
            <span className="hidden flex-1 text-left xl:inline">Search or jump to…</span>
            <kbd className="hidden rounded border border-border px-1.5 py-px font-mono-figures text-[11px] text-ink-2 lg:inline">
              Ctrl K
            </kbd>
          </button>
          <button
            type="button"
            onClick={() => void refresh.refresh()}
            disabled={refresh.pending}
            title={refresh.title}
            aria-label={refresh.title}
            className="flex h-10 items-center gap-2 rounded-md px-2 whitespace-nowrap text-ink-muted transition-colors hover:bg-muted hover:text-ink disabled:opacity-60"
          >
            {refresh.pending ? (
              <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <span className="hidden lg:contents">
                <HealthDot />
              </span>
            )}
            <RefreshCw className={cn("size-4 lg:hidden", refresh.pending && "hidden")} aria-hidden="true" />
          </button>
          <PendingBell />
          <IconButton label={privacy ? "Show amounts (Shift+P)" : "Hide amounts (Shift+P)"} onClick={togglePrivacyMode}>
            {privacy ? <EyeOff className="size-[18px]" aria-hidden="true" /> : <Eye className="size-[18px]" aria-hidden="true" />}
          </IconButton>
          <IconButton label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggleTheme}>
            {theme === "dark" ? <Sun className="size-[18px]" aria-hidden="true" /> : <Moon className="size-[18px]" aria-hidden="true" />}
          </IconButton>
          <Button variant="outline" size="lg" onClick={() => openAddAccount()} aria-label="Add account">
            <Plus className="size-4" aria-hidden="true" />
            <span className="hidden lg:inline">Add</span>
          </Button>
          <Button size="lg" onClick={() => setQuickUpdateOpen(true)}>
            Quick update
          </Button>
        </div>
        <div className="flex items-center gap-6 lg:gap-7">
          <nav aria-label="Main" className="flex min-w-0 flex-1 flex-wrap items-center gap-x-5 lg:gap-x-7">
            <NavLink to="/" end className={navLinkClass}>
              Overview
            </NavLink>
            <PeopleMenu />
            {SECTION_LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} className={navLinkClass}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <nav aria-label="Tools" className="flex items-center gap-5">
            {tools.map((l) => (
              <NavLink key={l.to} to={l.to} className={toolLinkClass}>
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>

      <AccountFormDialog
        open={addAccountOpen}
        onOpenChange={setAddAccountOpen}
        defaultCategory={addAccountDefaults?.category}
        defaultWrapper={addAccountDefaults?.wrapper}
      />
      <QuickUpdateSheet open={quickUpdateOpen} onOpenChange={setQuickUpdateOpen} />
    </header>
  )
}
