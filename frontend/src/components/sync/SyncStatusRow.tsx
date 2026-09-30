import { Link2, RefreshCw } from "lucide-react"
import { NavLink } from "react-router"
import { useSyncClient } from "@/api/hooks/useSync"
import { setSyncReportOpen } from "@/lib/appDialogs"
import { timeAgo } from "@/lib/dates"
import { useRunSync } from "@/lib/sync"
import { cn } from "@/lib/utils"

/** Phone only, in the navigation drawer: when it last synced, what's waiting, and Sync now. */
export function SyncStatusRow({ onAction }: { onAction?: () => void }) {
  const { data: client } = useSyncClient()
  const { run, isPending } = useRunSync()

  if (!client?.paired) {
    return (
      <NavLink
        to="/settings"
        onClick={onAction}
        className="flex items-center gap-2 rounded-md px-2.5 py-2.5 text-sm text-primary hover:bg-muted"
      >
        <Link2 className="size-4" aria-hidden="true" />
        Pair with your PC
      </NavLink>
    )
  }

  const pending = client.pending_changes
  return (
    <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5">
      <button
        type="button"
        onClick={() => {
          onAction?.()
          setSyncReportOpen(true)
        }}
        className="min-w-0 flex-1 text-left"
      >
        <p className="truncate text-sm text-ink">
          {client.last_sync_at ? `Synced ${timeAgo(client.last_sync_at)}` : "Not synced yet"}
        </p>
        <p className={cn("truncate text-xs", pending > 0 ? "text-warn" : "text-ink-muted")}>
          {pending > 0 ? `${pending} change${pending === 1 ? "" : "s"} waiting` : `with ${client.pc_name || "your PC"}`}
        </p>
      </button>
      <button
        type="button"
        onClick={() => void run()}
        disabled={isPending}
        className="flex size-9 items-center justify-center rounded-md text-ink-2 hover:bg-muted hover:text-ink disabled:opacity-50"
        aria-label="Sync now"
        title="Sync now"
      >
        <RefreshCw className={cn("size-4", isPending && "animate-spin")} aria-hidden="true" />
      </button>
    </div>
  )
}
