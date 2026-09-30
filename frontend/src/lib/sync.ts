import { useCallback, useEffect, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { type SyncClient, useRole, useSyncClient, useSyncNow } from "@/api/hooks/useSync"
import { apiErrorMessage } from "@/lib/api-error"
import { setSyncReportOpen } from "@/lib/appDialogs"

const AUTO_SYNC_MS = 15 * 60_000
const RESUME_MIN_GAP_MS = 2 * 60_000

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`
}

/** Runs a sync on the phone. `quiet` (automatic syncs) only speaks up about things that
 *  need attention: changes the PC turned down. */
export function useRunSync() {
  const syncNow = useSyncNow()
  const queryClient = useQueryClient()

  const run = useCallback(
    async (quiet = false) => {
      // Read at call time: straight after pairing, the name isn't in any render's props yet.
      const pcName = queryClient.getQueryData<SyncClient>(["sync", "client"])?.pc_name || "your PC"
      try {
        const report = await syncNow.mutateAsync()
        if (report.status === "ok") {
          const rejected = report.rejected?.length ?? 0
          const applied = report.applied ?? 0
          if (rejected > 0) {
            toast.warning(`${plural(rejected, "change")} ${rejected === 1 ? "wasn't" : "weren't"} accepted by ${pcName}`, {
              action: { label: "Details", onClick: () => setSyncReportOpen(true) },
            })
          } else if (!quiet) {
            toast.success(
              applied > 0
                ? `Synced with ${pcName}: ${plural(applied, "change")} sent`
                : `Up to date with ${pcName}`
            )
          }
        } else if (!quiet && report.status === "pc_unreachable") {
          toast.info(`Couldn't reach ${pcName}. Check you're on home Wi-Fi and Waymark is open on the PC.`)
        } else if (!quiet && report.status !== "already_running") {
          toast.warning(report.message || "The sync didn't finish; nothing was changed. Try again.")
        }
        return report
      } catch (err) {
        if (!quiet) toast.error(apiErrorMessage(err, "Could not sync"))
        return null
      }
    },
    [syncNow, queryClient]
  )

  return { run, isPending: syncNow.isPending }
}

/** Phone only: sync when the app opens, every 15 minutes while it's open, and when it comes
 *  back to the foreground (at most every 2 minutes). Silent unless something needs attention. */
export function useAutoSync() {
  const role = useRole()
  const { data: client } = useSyncClient(role === "phone")
  const { run } = useRunSync()
  const paired = role === "phone" && !!client?.paired
  const lastRun = useRef(0)
  const runRef = useRef(run)
  useEffect(() => {
    runRef.current = run
  }, [run])

  useEffect(() => {
    if (!paired) return
    function go() {
      lastRun.current = Date.now()
      void runRef.current(true)
    }
    go()
    const timer = window.setInterval(go, AUTO_SYNC_MS)
    function onVisible() {
      if (document.visibilityState === "visible" && Date.now() - lastRun.current > RESUME_MIN_GAP_MS) go()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [paired])
}
