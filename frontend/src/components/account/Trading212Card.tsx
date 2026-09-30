import { Link } from "react-router"
import { toast } from "sonner"
import {
  useDisconnectTrading212,
  useSetTrading212AutoSync,
  useSyncTrading212,
  useTrading212Link,
} from "@/api/hooks/useTrading212"
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
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { apiErrorMessage } from "@/lib/api-error"
import { trading212StatusLine } from "@/lib/trading212"
import { showTrading212Changes } from "@/lib/trading212Changes"

/** Link a holdings account to Trading 212's API so orders, dividends and cash movements arrive
 * by themselves (services/trading212_service.py). PC only: the phone gets the results by sync. */
export function Trading212Card({ accountId }: { accountId: number }) {
  const { data: link, isLoading } = useTrading212Link(accountId)
  const disconnect = useDisconnectTrading212()
  const sync = useSyncTrading212()
  const setAutoSync = useSetTrading212AutoSync()

  async function doSync() {
    try {
      await sync.mutateAsync(accountId)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not start a sync"))
    }
  }

  async function doDisconnect() {
    try {
      await disconnect.mutateAsync(accountId)
      toast.success("Trading 212 unlinked. Transactions already synced are kept.")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not unlink"))
    }
  }

  if (isLoading) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trading 212 sync</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        {!link ? (
          <p className="text-ink-2">
            Not connected. To pull this account's trades straight from Trading 212, go to{" "}
            <Link to="/settings" className="text-primary hover:underline">
              Settings → Trading 212
            </Link>{" "}
            and add it as an account you already track.
          </p>
        ) : (
          <>
            <div>
              <p className="text-ink">
                Linked{link.environment === "demo" ? " (practice account)" : ""} · key ending {link.key_hint}
              </p>
              <p className={link.status === "error" ? "text-xs text-loss" : "text-xs text-ink-muted"}>
                {trading212StatusLine(link)}
              </p>
              {link.status_message && link.status !== "running" && (
                <p className={link.status === "error" ? "mt-1 text-xs text-loss" : "mt-1 text-xs text-warn"}>
                  {link.status_message}
                </p>
              )}
            </div>

            {link.status === "needs_review" && link.pending_batch_id !== null && (
              <Button className="w-fit" onClick={() => showTrading212Changes(link.pending_batch_id!)}>
                Review changes
              </Button>
            )}

            <p className="text-xs text-ink-muted">
              Regular Payments on this account still count in projections, but aren't added on their own: the real
              payment arrives from Trading 212 when it lands.
            </p>

            <div className="flex items-center justify-between">
              <Label htmlFor="t212-auto">Sync daily and when the app opens</Label>
              <Switch
                id="t212-auto"
                checked={link.auto_sync}
                onCheckedChange={(checked) => setAutoSync.mutate({ accountId, autoSync: checked })}
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => void doSync()} disabled={link.status === "running" || sync.isPending}>
                {link.status === "running" ? "Syncing…" : "Sync now"}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger render={<Button variant="ghost" className="text-ink-muted hover:text-loss" />}>
                  Unlink
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Unlink Trading 212?</AlertDialogTitle>
                    <AlertDialogDescription>
                      The saved API key is deleted and syncing stops. Transactions already synced stay. You can
                      also revoke the key in the Trading 212 app.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction variant="destructive" onClick={() => void doDisconnect()}>
                      Unlink
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
