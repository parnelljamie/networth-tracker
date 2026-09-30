import { QrCode } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { useForgetPc, usePairWithPc, useSyncClient } from "@/api/hooks/useSync"
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { canScanQr, scanQr } from "@/lib/android"
import { apiErrorMessage } from "@/lib/api-error"
import { setSyncReportOpen } from "@/lib/appDialogs"
import { timeAgo } from "@/lib/dates"
import { useRunSync } from "@/lib/sync"

/** Phone Settings: pair with the PC, sync, and see how the last sync went. */
export function PcSyncCard() {
  const { data: client } = useSyncClient()
  const pairWithPc = usePairWithPc()
  const forget = useForgetPc()
  const { run, isPending } = useRunSync()
  const [link, setLink] = useState("")

  async function pair(uri: string) {
    try {
      const result = await pairWithPc.mutateAsync(uri.trim())
      setLink("")
      toast.success(`Paired with ${result.pc_name || "your PC"}`)
      await run()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not pair with the PC"))
    }
  }

  async function scan() {
    const text = await scanQr()
    if (text) await pair(text)
  }

  async function unpair() {
    try {
      await forget.mutateAsync()
      toast.success("This phone is no longer paired")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not unpair"))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your PC</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {!client?.paired ? (
          <>
            <p className="text-ink-2">
              Your PC holds the master copy. On the PC, open Waymark's Settings → Phone, turn on phone syncing
              and choose <span className="text-ink">Pair a phone</span>. Then scan the code it shows.
            </p>
            {canScanQr() && (
              <Button onClick={() => void scan()} disabled={pairWithPc.isPending}>
                <QrCode className="size-4" aria-hidden="true" />
                Scan the pairing code
              </Button>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pairing-link">{canScanQr() ? "Or paste the pairing link" : "Pairing link"}</Label>
              <div className="flex gap-2">
                <Input
                  id="pairing-link"
                  value={link}
                  placeholder="passbook://pair?…"
                  onChange={(e) => setLink(e.target.value)}
                  className="font-mono-figures"
                />
                <Button
                  variant="outline"
                  onClick={() => void pair(link)}
                  disabled={!link.trim() || pairWithPc.isPending}
                >
                  Pair
                </Button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-ink">Paired with {client.pc_name || "your PC"}</p>
              <p className="text-xs text-ink-muted">
                {client.last_sync_at ? `Last synced ${timeAgo(client.last_sync_at)}` : "Not synced yet"}
                {client.pending_changes > 0 &&
                  ` · ${client.pending_changes} change${client.pending_changes === 1 ? "" : "s"} waiting to send`}
              </p>
            </div>
            <p className="text-xs text-ink-muted">
              Syncs by itself when you open the app and every 15 minutes while it's open, whenever the phone is on
              the same Wi-Fi as the PC and Waymark is open there.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void run()} disabled={isPending}>
                {isPending ? "Syncing…" : "Sync now"}
              </Button>
              <Button variant="outline" onClick={() => setSyncReportOpen(true)}>
                Last sync details
              </Button>
              <AlertDialog>
                <AlertDialogTrigger render={<Button variant="ghost" className="text-ink-muted hover:text-loss" />}>
                  Unpair
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Unpair from {client.pc_name || "your PC"}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This phone keeps its current figures but stops syncing.
                      {client.pending_changes > 0 &&
                        ` The ${client.pending_changes} change${client.pending_changes === 1 ? "" : "s"} waiting won't reach the PC.`}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction variant="destructive" onClick={() => void unpair()}>
                      Unpair
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
