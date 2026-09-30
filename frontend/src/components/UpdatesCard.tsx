import { useState } from "react"
import { toast } from "sonner"
import { useCheckForUpdate, useInstallUpdate, useSystemInfo, useUpdateStatus } from "@/api/hooks/useSettings"
import { Pct } from "@/components/Pct"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { type AndroidUpdateStatus, canInstallAndroidUpdate, installAndroidUpdate } from "@/lib/android"
import { apiErrorMessage } from "@/lib/api-error"

interface Progress {
  state: string
  downloaded?: number
  total?: number | null
  error?: string | null
}

function ProgressLine({ progress, onAndroid }: { progress: Progress; onAndroid: boolean }) {
  if (progress.state === "downloading") {
    return (
      <p className="text-sm text-ink-muted">
        Downloading
        {progress.total ? (
          <>
            {" "}
            <Pct value={(progress.downloaded ?? 0) / progress.total} decimals={0} />
          </>
        ) : (
          "…"
        )}
      </p>
    )
  }
  if (progress.state === "installing") {
    return (
      <p className="text-sm text-ink-muted">
        {onAndroid
          ? "Tap Install on Android's screen. Your data and pairing stay as they are."
          : "Installing. Waymark will close and reopen by itself."}
      </p>
    )
  }
  if (progress.state === "permission") {
    return (
      <p className="text-sm text-ink-muted">
        Turn on "Allow from this source" for Waymark in the screen that just opened, then come back and tap Update now
        again.
      </p>
    )
  }
  if (progress.state === "error") {
    return <p className="text-sm text-loss">{progress.error || "The update didn't finish. Try again."}</p>
  }
  return null
}

/** Settings -> Updates: check GitHub for a newer release and install it (docs/05-ui.md). */
export function UpdatesCard() {
  const { data: systemInfo } = useSystemInfo()
  const check = useCheckForUpdate()
  const install = useInstallUpdate()
  const info = check.data
  const { data: pcStatus } = useUpdateStatus(install.isSuccess)
  const [androidStatus, setAndroidStatus] = useState<AndroidUpdateStatus | null>(null)

  const onAndroid = info?.platform === "android"
  const canInstallHere = info ? (onAndroid ? canInstallAndroidUpdate() : info.can_install) : false
  const progress: Progress | null = onAndroid ? androidStatus : (pcStatus ?? null)
  const busy = progress?.state === "downloading" || progress?.state === "installing"

  async function runCheck() {
    try {
      const result = await check.mutateAsync()
      if (!result.update_available) toast.success(`You're on the latest version (${result.current_version})`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't check for updates"))
    }
  }

  async function updateNow() {
    if (!info) return
    if (onAndroid) {
      if (!info.asset_url) return
      setAndroidStatus({ state: "downloading" })
      installAndroidUpdate(info.asset_url, info.asset_sha256 ?? null, setAndroidStatus)
      return
    }
    try {
      await install.mutateAsync()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't start the update"))
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Updates</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-ink-muted">
            {info?.update_available ? (
              <>
                Version <span className="text-ink">{info.latest_version}</span> is available. You have{" "}
                {info.current_version}.
              </>
            ) : (
              <>
                You have Waymark <span className="text-ink">{systemInfo ? `v${systemInfo.version}` : ""}</span>.
                {info && " It's the latest version."}
              </>
            )}
          </p>
          <div className="ml-auto flex flex-wrap gap-2">
            {info?.update_available && (
              <a
                href={info.release_url}
                target="_blank"
                rel="noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                What's new
              </a>
            )}
            {info?.update_available && canInstallHere && (
              <Button size="sm" onClick={updateNow} disabled={busy || install.isPending}>
                Update now
              </Button>
            )}
            {info?.update_available && !canInstallHere && info.asset_url && (
              <a href={info.asset_url} target="_blank" rel="noreferrer" className={buttonVariants({ size: "sm" })}>
                Download {info.asset_name}
              </a>
            )}
            {!info?.update_available && (
              <Button variant="outline" size="sm" onClick={runCheck} disabled={check.isPending}>
                {check.isPending ? "Checking…" : "Check for updates"}
              </Button>
            )}
          </div>
        </div>
        {progress && <ProgressLine progress={progress} onAndroid={onAndroid} />}
        {info?.update_available && info.platform === "linux" && (
          <p className="text-sm text-ink-muted">
            Install it with <span className="font-mono text-ink">sudo apt install ./{info.asset_name}</span>. Your data
            stays where it is.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
