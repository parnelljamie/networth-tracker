import { CirclePlus, Eye, EyeOff, Moon, Search, Sun } from "lucide-react"
import { NavLink } from "react-router"
import { useNetWorthCurrent } from "@/api/hooks/useNetworth"
import { usePeople } from "@/api/hooks/usePeople"
import { useRole } from "@/api/hooks/useSync"
import { Money } from "@/components/Money"
import { PersonAvatar } from "@/components/PersonAvatar"
import { SyncStatusRow } from "@/components/sync/SyncStatusRow"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { openAddAccount } from "@/lib/appDialogs"
import { openCommandPalette } from "@/lib/commandPalette"
import { togglePrivacyMode, usePrivacyMode } from "@/lib/privacy"
import { toggleTheme, useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"
import { HealthDot } from "./HealthDot"
import { Wordmark } from "./Masthead"
import { SECTION_LINKS, TOOL_LINKS } from "./nav"

const rowClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-12 items-center gap-3 border-l-[3px] px-4 text-base transition-colors",
    isActive ? "border-ink font-semibold text-ink" : "border-transparent text-ink-2 hover:bg-muted hover:text-ink"
  )

/** Phones: the masthead's navigation in a drawer from the left; tapping any link closes it. */
export function NavDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const privacy = usePrivacyMode()
  const theme = useTheme()
  const { data: people } = usePeople()
  const { data: networth } = useNetWorthCurrent()
  const role = useRole()
  const close = () => onOpenChange(false)
  // Imports belong on the PC: the phone's copy is replaced at every sync.
  const tools = role === "phone" ? TOOL_LINKS.filter((l) => l.to !== "/import") : TOOL_LINKS

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[300px] gap-0 p-0 md:hidden">
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <div className="flex flex-col gap-1 border-b border-border px-5 pt-6 pb-5">
          <Wordmark onClick={close} className="[&>span:last-child]:text-[22px] [&>svg]:h-[17px]" />
          <span className="mt-3 text-xs text-ink-muted">Household</span>
          <Money value={networth?.total_gbp ?? 0} display whole className="text-[32px] leading-none text-ink" />
        </div>

        <nav aria-label="Main" className="flex flex-1 flex-col overflow-y-auto py-2">
          <button
            type="button"
            className={rowClass({ isActive: false })}
            onClick={() => {
              close()
              openCommandPalette()
            }}
          >
            <Search className="size-4" aria-hidden="true" />
            Search
          </button>
          <button
            type="button"
            className={rowClass({ isActive: false })}
            onClick={() => {
              close()
              openAddAccount()
            }}
          >
            <CirclePlus className="size-4" aria-hidden="true" />
            Add account
          </button>
          <div className="my-2 border-t border-border" />
          <NavLink to="/" end className={rowClass} onClick={close}>
            Overview
          </NavLink>
          {SECTION_LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} className={rowClass} onClick={close}>
              {l.label === "Other" ? "Other assets" : l.label}
            </NavLink>
          ))}
          {people && people.length > 0 && (
            <>
              <span className="eyebrow mt-3 px-4 pt-2 pb-1">People</span>
              {people.map((person) => (
                <NavLink key={person.id} to={`/people/${person.id}`} className={rowClass} onClick={close}>
                  <PersonAvatar name={person.name} color={person.color} />
                  {person.name}
                </NavLink>
              ))}
            </>
          )}
          <div className="my-2 border-t border-border" />
          {tools.map((l) => (
            <NavLink key={l.to} to={l.to} className={rowClass} onClick={close}>
              {l.label}
            </NavLink>
          ))}
        </nav>

        {role === "phone" && (
          <div className="border-t border-border px-2 py-1">
            <SyncStatusRow onAction={close} />
          </div>
        )}
        <div className="flex items-center gap-1 border-t border-border py-2 pr-2 pl-4">
          <span className="flex-1">
            <HealthDot />
          </span>
          <button
            type="button"
            onClick={togglePrivacyMode}
            className="flex size-11 items-center justify-center rounded-md text-ink-2 hover:bg-muted hover:text-ink"
            aria-label={privacy ? "Show amounts" : "Hide amounts"}
          >
            {privacy ? <EyeOff className="size-5" aria-hidden="true" /> : <Eye className="size-5" aria-hidden="true" />}
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            className="flex size-11 items-center justify-center rounded-md text-ink-2 hover:bg-muted hover:text-ink"
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun className="size-5" aria-hidden="true" /> : <Moon className="size-5" aria-hidden="true" />}
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
