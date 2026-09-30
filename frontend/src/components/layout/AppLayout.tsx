import { useState } from "react"
import { Outlet } from "react-router"
import { CommandPalette } from "@/components/CommandPalette"
import { SyncReportDialog } from "@/components/sync/SyncReportDialog"
import { Trading212ChangesDialog } from "@/components/Trading212ChangesDialog"
import { useAutoSync } from "@/lib/sync"
import { cn } from "@/lib/utils"
import { Masthead } from "./Masthead"
import { COLUMN } from "./nav"
import { NavDrawer } from "./NavDrawer"

// Desktop: the masthead stays put and the page scrolls beneath it. Phones: the whole page
// scrolls under a sticky bar, so the browser chrome can collapse as usual.
export function AppLayout() {
  const [navOpen, setNavOpen] = useState(false)
  useAutoSync()

  return (
    <div className="flex min-h-full flex-col md:h-full">
      <Masthead onOpenNav={() => setNavOpen(true)} />
      <NavDrawer open={navOpen} onOpenChange={setNavOpen} />
      <div className="flex min-w-0 flex-1 flex-col md:overflow-y-auto">
        <main className={cn(COLUMN, "min-w-0 flex-1 overflow-x-hidden py-6 md:py-10")}>
          <Outlet />
        </main>
      </div>
      <CommandPalette />
      <SyncReportDialog />
      <Trading212ChangesDialog />
    </div>
  )
}
