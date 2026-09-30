import QRCode from "qrcode"
import { Smartphone } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { usePairPhone, useSetSyncEnabled, useSyncStatus, useUnpairPhone } from "@/api/hooks/useSync"
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
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { apiErrorMessage } from "@/lib/api-error"
import { timeAgo } from "@/lib/dates"

/** PC Settings: let the Android app sync with this PC (docs/07-mobile.md). */
export function PhoneSyncCard() {
  const { data: status } = useSyncStatus()
  const setEnabled = useSetSyncEnabled()
  const unpair = useUnpairPhone()
  const [pairOpen, setPairOpen] = useState(false)

  async function toggle(enabled: boolean) {
    try {
      await setEnabled.mutateAsync(enabled)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not change phone syncing"))
    }
  }

  async function remove(id: number, name: string) {
    try {
      await unpair.mutateAsync(id)
      toast.success(`${name} can no longer sync with this PC`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not unpair that phone"))
    }
  }

  const enabled = !!status?.enabled
  return (
    <Card>
      <CardHeader>
        <CardTitle>Phone</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <p className="text-ink-2">
          Waymark on your Android phone keeps a copy of your figures and sends back anything you change on it,
          whenever the phone and this PC are on the same Wi-Fi. This PC stays the master copy.
        </p>

        <div className="flex items-center justify-between gap-3">
          <div>
            <Label htmlFor="sync-enabled">Let phones sync with this PC</Label>
            <p className="text-xs text-ink-muted">
              {enabled && status?.running
                ? `Listening on your home network at ${status.addresses.join(", ") || "this PC"} (port ${status.port})`
                : "Off: nothing on this PC is reachable from your network."}
            </p>
          </div>
          <Switch
            id="sync-enabled"
            checked={enabled}
            disabled={setEnabled.isPending || !status}
            onCheckedChange={(checked) => void toggle(checked)}
          />
        </div>
        {enabled && status && status.addresses.length === 0 && (
          <p className="text-xs text-warn">This PC doesn't seem to be on a network, so a phone won't find it.</p>
        )}

        {status && status.devices.length > 0 && (
          <div className="flex flex-col divide-y divide-border rounded-lg border border-border">
            {status.devices.map((d) => (
              <div key={d.id} className="flex items-center gap-3 p-3">
                <Smartphone className="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-ink">{d.name}</p>
                  <p className="text-xs text-ink-muted">
                    {d.last_sync_at ? `Last synced ${timeAgo(d.last_sync_at)}` : "Paired, not synced yet"}
                  </p>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger
                    render={<Button variant="ghost" size="sm" className="text-ink-muted hover:text-loss" />}
                  >
                    Unpair
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Unpair {d.name}?</AlertDialogTitle>
                      <AlertDialogDescription>
                        It won't be able to sync with this PC again until you pair it afresh. Changes made on it
                        since its last sync won't reach this PC.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction variant="destructive" onClick={() => void remove(d.id, d.name)}>
                        Unpair
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))}
          </div>
        )}

        <div>
          <Button variant="outline" size="sm" disabled={!enabled} onClick={() => setPairOpen(true)}>
            Pair a phone
          </Button>
        </div>
      </CardContent>
      <PairPhoneDialog open={pairOpen} onOpenChange={setPairOpen} />
    </Card>
  )
}

function PairPhoneDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const pair = usePairPhone()
  const [name, setName] = useState("My phone")
  const [link, setLink] = useState<string | null>(null)
  const [qr, setQr] = useState<string | null>(null)

  useEffect(() => {
    if (!link) return
    let cancelled = false
    QRCode.toDataURL(link, { margin: 1, width: 240, errorCorrectionLevel: "M" })
      .then((url) => {
        if (!cancelled) setQr(url)
      })
      .catch(() => toast.error("Could not draw the QR code; use the link instead"))
    return () => {
      cancelled = true
    }
  }, [link])

  function close(next: boolean) {
    onOpenChange(next)
    if (!next) {
      // The link is a secret: don't keep it around once the dialog is closed.
      setLink(null)
      setQr(null)
      pair.reset()
    }
  }

  async function create() {
    try {
      const result = await pair.mutateAsync(name.trim())
      setLink(result.pairing_uri)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not pair a phone"))
    }
  }

  async function copy() {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      toast.success("Pairing link copied")
    } catch {
      toast.error("Couldn't copy; select the link and copy it instead")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Pair a phone</DialogTitle>
          <DialogDescription>
            {link
              ? "In Waymark on the phone, open Settings → Your PC and scan this code."
              : "Give the phone a name so you can tell it apart here."}
          </DialogDescription>
        </DialogHeader>
        {!link ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="phone-name">Phone name</Label>
              <Input id="phone-name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
            </div>
            <Button onClick={() => void create()} disabled={!name.trim() || pair.isPending}>
              Show pairing code
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            {qr ? (
              <img src={qr} alt="Pairing QR code" className="size-60 rounded-lg bg-white p-2" />
            ) : (
              <div className="size-60 rounded-lg bg-muted" />
            )}
            <p className="text-center text-xs text-ink-muted">
              Anyone who scans this code on your Wi-Fi can read your Waymark data, so close this once the phone
              is paired. You can unpair a phone at any time.
            </p>
            <details className="w-full text-xs">
              <summary className="cursor-pointer text-ink-2">Can't scan? Use the link</summary>
              <p className="mt-2 break-all rounded-md border border-border bg-muted p-2 font-mono-figures text-ink select-all">
                {link}
              </p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => void copy()}>
                Copy link
              </Button>
            </details>
            <Button className="w-full" onClick={() => close(false)}>
              Done
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
