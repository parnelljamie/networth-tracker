import { CircleCheck, CircleX } from "lucide-react"
import { useRole, useSyncClient } from "@/api/hooks/useSync"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { setSyncReportOpen, useDialogsState } from "@/lib/appDialogs"
import { formatDate, timeAgo } from "@/lib/dates"

/** Phone: what the last sync sent to the PC, and anything the PC turned down. */
export function SyncReportDialog() {
  const { syncReportOpen } = useDialogsState()
  const role = useRole()
  const { data: client } = useSyncClient(role === "phone")
  const report = client?.last_report
  const rejected = report?.rejected ?? []
  const applied = report?.applied ?? 0

  return (
    <Dialog open={syncReportOpen} onOpenChange={setSyncReportOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Last sync</DialogTitle>
          <DialogDescription>
            {report?.at
              ? `With ${client?.pc_name || "your PC"}, ${timeAgo(report.at)} (${formatDate(report.at)})`
              : "This phone hasn't synced yet."}
          </DialogDescription>
        </DialogHeader>
        {report && (
          <div className="flex flex-col gap-3 text-sm">
            <p className="flex items-center gap-2 text-ink">
              <CircleCheck className="size-4 text-gain" aria-hidden="true" />
              {applied === 0
                ? "No changes from this phone needed sending."
                : `${applied} change${applied === 1 ? "" : "s"} from this phone saved on the PC.`}
            </p>
            {rejected.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="text-ink">
                  {rejected.length} change{rejected.length === 1 ? " wasn't" : "s weren't"} accepted by the PC, so
                  {rejected.length === 1 ? " it's" : " they're"} no longer on this phone:
                </p>
                <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
                  {rejected.map((r, i) => (
                    <li key={i} className="flex gap-2 p-2.5">
                      <CircleX className="mt-0.5 size-4 shrink-0 text-loss" aria-hidden="true" />
                      <div className="min-w-0">
                        <p className="text-ink">{r.summary}</p>
                        {r.message && <p className="text-xs text-ink-muted">The PC said: {r.message}</p>}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {(client?.pending_changes ?? 0) > 0 && (
          <p className="text-xs text-ink-muted">
            {client?.pending_changes} newer change{client?.pending_changes === 1 ? " is" : "s are"} waiting for the
            next sync.
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
