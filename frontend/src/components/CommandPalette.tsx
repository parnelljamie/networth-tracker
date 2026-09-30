import { useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"
import { useAccounts } from "@/api/hooks/useAccounts"
import { useRefreshPrices } from "@/api/hooks/useInstruments"
import { usePeople } from "@/api/hooks/usePeople"
import { useRole } from "@/api/hooks/useSync"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { openAddAccount, openQuickUpdate } from "@/lib/appDialogs"
import { apiErrorMessage } from "@/lib/api-error"
import { closeCommandPalette, useCommandPaletteOpen } from "@/lib/commandPalette"
import { togglePrivacyMode } from "@/lib/privacy"

const PAGE_COMMANDS = [
  { label: "Overview", to: "/" },
  { label: "Property & Mortgage", to: "/property" },
  { label: "Other assets", to: "/other" },
  { label: "Projections", to: "/projections" },
  { label: "Import", to: "/import" },
  { label: "Settings", to: "/settings" },
]

function matches(label: string, query: string): boolean {
  return label.toLowerCase().includes(query.trim().toLowerCase())
}

/**
 * `Ctrl+K` / `Cmd+K` command palette (docs/05-ui.md app shell): jump to any page/account,
 * run "Refresh prices", "Quick update", "Add account", toggle privacy. Instrument search is
 * skipped — this app has no per-instrument detail page/route yet, only account pages.
 */
export function CommandPalette() {
  const open = useCommandPaletteOpen()
  const navigate = useNavigate()
  const { data: people } = usePeople()
  const { data: accounts } = useAccounts()
  const refreshPrices = useRefreshPrices()
  const role = useRole()
  const pageCommands = role === "phone" ? PAGE_COMMANDS.filter((c) => c.to !== "/import") : PAGE_COMMANDS
  const [search, setSearch] = useState("")

  function close() {
    closeCommandPalette()
    setSearch("")
  }

  function go(to: string) {
    close()
    navigate(to)
  }

  async function runRefreshPrices() {
    close()
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

  function runQuickUpdate() {
    close()
    openQuickUpdate()
  }

  function runAddAccount() {
    close()
    openAddAccount()
  }

  function runTogglePrivacy() {
    close()
    togglePrivacyMode()
  }

  const matchedPages = pageCommands.filter((p) => matches(p.label, search))
  const matchedPeople = (people ?? []).filter((p) => matches(p.name, search))
  const matchedAccounts = (accounts ?? []).filter((a) => matches(a.name, search)).slice(0, 20)
  const actionCommands = [
    { label: "Quick update", run: runQuickUpdate },
    { label: "Add account", run: runAddAccount },
    { label: "Refresh prices", run: runRefreshPrices },
    { label: "Toggle privacy", run: runTogglePrivacy },
  ]
  const matchedActions = actionCommands.filter((a) => matches(a.label, search))

  const nothingMatched =
    matchedPages.length === 0 &&
    matchedPeople.length === 0 &&
    matchedAccounts.length === 0 &&
    matchedActions.length === 0

  return (
    <CommandDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) closeCommandPalette()
      }}
    >
      <Command shouldFilter={false}>
        <CommandInput
          value={search}
          onValueChange={setSearch}
          placeholder="Jump to a page, account, or run a command…"
        />
        <CommandList>
          {nothingMatched && <CommandEmpty>No matches.</CommandEmpty>}

          {matchedActions.length > 0 && (
            <CommandGroup heading="Commands">
              {matchedActions.map((action) => (
                <CommandItem key={action.label} value={action.label} onSelect={action.run}>
                  {action.label}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {matchedPages.length > 0 && (
            <>
              {matchedActions.length > 0 && <CommandSeparator />}
              <CommandGroup heading="Pages">
                {matchedPages.map((page) => (
                  <CommandItem key={page.to} value={page.label} onSelect={() => go(page.to)}>
                    {page.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {matchedPeople.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="People">
                {matchedPeople.map((person) => (
                  <CommandItem
                    key={person.id}
                    value={`person-${person.id}`}
                    onSelect={() => go(`/people/${person.id}`)}
                  >
                    {person.name}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}

          {matchedAccounts.length > 0 && (
            <>
              <CommandSeparator />
              <CommandGroup heading="Accounts">
                {matchedAccounts.map((account) => (
                  <CommandItem
                    key={account.id}
                    value={`account-${account.id}`}
                    onSelect={() => go(`/accounts/${account.id}`)}
                  >
                    {account.name}
                    {account.provider ? ` · ${account.provider}` : ""}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
