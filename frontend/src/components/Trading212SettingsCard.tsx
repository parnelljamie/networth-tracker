import { useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"
import { useAccounts } from "@/api/hooks/useAccounts"
import { usePeople } from "@/api/hooks/usePeople"
import {
  useConnectTrading212,
  useConnectTrading212NewAccount,
  useSyncTrading212,
  useTrading212Links,
} from "@/api/hooks/useTrading212"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api-error"
import { trading212StatusLine } from "@/lib/trading212"
import { showTrading212Changes } from "@/lib/trading212Changes"

type AccountType = "isa" | "invest"

const SELECT_CLASS = "h-9 w-full rounded-md border border-border bg-card px-2 text-sm text-ink"

/** Settings → Trading 212: every linked account, plus connecting a new one. Trading 212's API
 * can't say whether a key belongs to a Stocks ISA or an Invest account, so the user picks and
 * the holdings account is created to match (or they link one they already track). */
export function Trading212SettingsCard() {
  const { data: links } = useTrading212Links()
  const { data: accounts } = useAccounts()
  const { data: people } = usePeople()
  const connectNew = useConnectTrading212NewAccount()
  const connectExisting = useConnectTrading212()
  const sync = useSyncTrading212()

  const [open, setOpen] = useState(false)
  const [apiKey, setApiKey] = useState("")
  const [apiSecret, setApiSecret] = useState("")
  const [environment, setEnvironment] = useState<"live" | "demo">("live")
  const [accountType, setAccountType] = useState<AccountType>("isa")
  const [target, setTarget] = useState<"new" | "existing">("new")
  const [ownerId, setOwnerId] = useState<number | undefined>(undefined)
  const [existingId, setExistingId] = useState<number | undefined>(undefined)

  const linkedIds = new Set((links ?? []).map((l) => l.account_id))
  const accountName = (id: number) => (accounts ?? []).find((a) => a.id === id)?.name ?? `Account ${id}`
  const linkable = (accounts ?? []).filter((a) => a.valuation_method === "holdings" && !linkedIds.has(a.id))
  const owner = ownerId ?? people?.[0]?.id
  const busy = connectNew.isPending || connectExisting.isPending
  const ready = apiKey.trim() !== "" && (target === "new" ? owner !== undefined : existingId !== undefined)

  function reset() {
    setApiKey("")
    setApiSecret("")
    setOpen(false)
  }

  async function doConnect() {
    try {
      const payload = { api_key: apiKey, api_secret: apiSecret, environment }
      const link =
        target === "new"
          ? await connectNew.mutateAsync({ ...payload, account_type: accountType, owner_person_id: owner! })
          : await connectExisting.mutateAsync({ accountId: existingId!, payload })
      if (!link) return
      reset()
      await sync.mutateAsync(link.account_id)
      toast.success("Connected. Fetching your history: the first sync can take a few minutes, and the changes pop up for you to accept when it's done.")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not connect to Trading 212"))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Trading 212</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <p className="text-ink-2">
          Connect a Trading 212 Stocks ISA or Invest account and its buys, sells, dividends and deposits arrive by
          themselves. Each account needs its own API key.
        </p>

        {(links ?? []).length > 0 && (
          <ul className="flex flex-col gap-2">
            {(links ?? []).map((link) => (
              <li key={link.account_id} className="flex items-center justify-between gap-3 border-t border-border pt-2">
                <div>
                  <Link to={`/accounts/${link.account_id}`} className="text-ink hover:underline">
                    {accountName(link.account_id)}
                  </Link>
                  <p className={link.status === "error" ? "text-xs text-loss" : "text-xs text-ink-muted"}>
                    {trading212StatusLine(link)}
                  </p>
                </div>
                {link.status === "needs_review" && link.pending_batch_id !== null ? (
                  <Button size="sm" onClick={() => showTrading212Changes(link.pending_batch_id!)}>
                    Review changes
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={link.status === "running" || sync.isPending}
                    onClick={() => void sync.mutateAsync(link.account_id).catch((err) => toast.error(apiErrorMessage(err, "Could not start a sync")))}
                  >
                    {link.status === "running" ? "Syncing…" : "Sync now"}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {!open ? (
          <Button variant={(links ?? []).length > 0 ? "outline" : "default"} className="w-fit" onClick={() => setOpen(true)}>
            Connect a Trading 212 account
          </Button>
        ) : (
          <div className="flex flex-col gap-4 rounded-lg border border-border p-4">
            <p className="text-ink-2">
              In the Trading 212 app, switch to the account you want, open Settings → API and create a key with read
              access to account data and history only. The app never places orders.
            </p>

            <div className="flex flex-col gap-1.5">
              <Label>Which Trading 212 account is the key for?</Label>
              <div className="flex gap-4">
                {(
                  [
                    ["isa", "Stocks ISA"],
                    ["invest", "Invest (general account)"],
                  ] as const
                ).map(([value, label]) => (
                  <label key={value} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="t212-type"
                      checked={accountType === value}
                      onChange={() => setAccountType(value)}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="t212s-key">API key</Label>
                <Input id="t212s-key" type="password" autoComplete="off" value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)} className="font-mono-figures" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="t212s-secret">API secret</Label>
                <Input id="t212s-secret" type="password" autoComplete="off" value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)} className="font-mono-figures" />
              </div>
            </div>
            <p className="-mt-2 text-xs text-ink-muted">
              Leave the secret blank if your key came without one. The key is stored encrypted on this PC only, never
              in the database, backups or the phone copy.
            </p>

            <div className="flex flex-col gap-1.5">
              <Label>Add it as</Label>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2">
                  <input type="radio" name="t212-target" checked={target === "new"} onChange={() => setTarget("new")} />
                  A new account
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="t212-target" checked={target === "existing"}
                    onChange={() => setTarget("existing")} disabled={linkable.length === 0} />
                  An account I already track
                </label>
              </div>
            </div>

            {target === "new" ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="t212s-owner">Whose account is it?</Label>
                <select id="t212s-owner" value={owner ?? ""} onChange={(e) => setOwnerId(Number(e.target.value))}
                  className={SELECT_CLASS}>
                  {(people ?? []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <p className="text-xs text-ink-muted">
                  Creates “{accountType === "isa" ? "Trading 212 Stocks ISA" : "Trading 212 Invest"}”. You can rename it
                  in its Settings tab.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="t212s-existing">Account</Label>
                <select id="t212s-existing" value={existingId ?? ""}
                  onChange={(e) => setExistingId(e.target.value ? Number(e.target.value) : undefined)}
                  className={SELECT_CLASS}>
                  <option value="">Select…</option>
                  {linkable.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}</option>
                  ))}
                </select>
                <p className="text-xs text-ink-muted">
                  Your first sync pops up for you to accept, so anything already recorded in this account isn't doubled.
                </p>
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="t212s-env">Money</Label>
              <select id="t212s-env" value={environment}
                onChange={(e) => setEnvironment(e.target.value as "live" | "demo")} className={`${SELECT_CLASS} w-fit`}>
                <option value="live">Real money</option>
                <option value="demo">Practice</option>
              </select>
            </div>

            <div className="flex gap-2">
              <Button onClick={() => void doConnect()} disabled={!ready || busy}>
                {busy ? "Checking the key…" : "Connect"}
              </Button>
              <Button variant="ghost" onClick={reset} disabled={busy}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
