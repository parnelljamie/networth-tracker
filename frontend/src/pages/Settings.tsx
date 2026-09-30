import { useState } from "react"
import { toast } from "sonner"
import { useCreatePerson, useDeletePerson, usePeople, useUpdatePerson } from "@/api/hooks/usePeople"
import {
  useBackups,
  useChooseFolder,
  useOpenDataFolder,
  usePatchSettings,
  useRunBackup,
  useSettings,
  useSystemInfo,
} from "@/api/hooks/useSettings"
import { useRole } from "@/api/hooks/useSync"
import { AboutCard } from "@/components/AboutCard"
import { PersonAvatar } from "@/components/PersonAvatar"
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
import { PageHeader } from "@/components/PageHeader"
import { DateInput } from "@/components/DateInput"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PcSyncCard } from "@/components/sync/PcSyncCard"
import { PhoneSyncCard } from "@/components/sync/PhoneSyncCard"
import { Trading212SettingsCard } from "@/components/Trading212SettingsCard"
import { UpdatesCard } from "@/components/UpdatesCard"
import { Switch } from "@/components/ui/switch"
import { Tooltip as HelpTip } from "@/components/ui/tooltip"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate, todayIso } from "@/lib/dates"

const SWATCHES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7", "#e34948"]

// Hover help for the People fields. Keep in step with the backend uses of these fields.
const PERSON_HELP = {
  colour: "Shown on this person's avatar so you can tell people apart at a glance.",
  dateOfBirth:
    "Needed for anything age-based: the pension access and retirement milestones on Projections, " +
    "projecting their pensions to retirement, and when a defined benefit pension stops building up.",
  retirementAge:
    "The age they stop working. Sets the retirement milestone, the date their pension pots are " +
    "projected to, and when an active defined benefit pension stops building up. Needs a date of birth.",
  inHousehold:
    "Counts this person's accounts, and their share of joint ones, in the household totals and " +
    "snapshots. Turn off to keep them out of the totals; they still have their own page.",
}

export function Settings() {
  const { data: people } = usePeople(true)
  const createPerson = useCreatePerson()
  const updatePerson = useUpdatePerson()
  const role = useRole()

  const [name, setName] = useState("")
  const [color, setColor] = useState(SWATCHES[0])

  async function addPerson() {
    if (!name.trim()) return
    try {
      await createPerson.mutateAsync({ name: name.trim(), color })
      toast.success(`${name} added`)
      setName("")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not add that person — name may already be in use"))
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-10">
      <PageHeader eyebrow="Waymark" title="Settings" />

      <Card>
        <CardHeader>
          <CardTitle>People</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-3">
            {(people ?? []).map((person) => (
              <PersonRow
                key={person.id}
                person={person}
                onUpdate={(payload) => updatePerson.mutate({ id: person.id, payload })}
              />
            ))}
            {(people ?? []).length === 0 && (
              <p className="text-sm text-ink-muted">No people yet — add your first below.</p>
            )}
          </div>

          <div className="flex flex-wrap items-end gap-2 border-t border-border pt-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-person-name">Name</Label>
              <Input
                id="new-person-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. James"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>
                <HelpTip content={PERSON_HELP.colour}>Colour</HelpTip>
              </Label>
              <div className="flex gap-1.5">
                {SWATCHES.map((swatch) => (
                  <button
                    key={swatch}
                    type="button"
                    onClick={() => setColor(swatch)}
                    className={`size-7 rounded-full ${color === swatch ? "ring-2 ring-offset-2 ring-primary" : ""}`}
                    style={{ backgroundColor: swatch }}
                    aria-label={`Choose colour ${swatch}`}
                  />
                ))}
              </div>
            </div>
            <Button onClick={addPerson} disabled={!name.trim() || createPerson.isPending}>
              Add person
            </Button>
          </div>
        </CardContent>
      </Card>

      {role === "phone" ? (
        // The phone's data lives in the app and is replaced at every sync; backups, export and
        // the data folder belong to the PC, which holds the master copy.
        <PcSyncCard />
      ) : (
        <>
          <Trading212SettingsCard />
          <PhoneSyncCard />
          <DataCard />
        </>
      )}

      <UpdatesCard />
      <AboutCard />
    </div>
  )
}

function DataCard() {
  const { data: backups } = useBackups()
  const { data: systemInfo } = useSystemInfo()
  const openDataFolder = useOpenDataFolder()
  const runBackup = useRunBackup()
  const { data: settings } = useSettings()
  const patchSettings = usePatchSettings()
  const chooseFolder = useChooseFolder()
  const savedCopyDir = (settings?.backup_copy_dir as string | undefined) ?? ""
  const [copyDir, setCopyDir] = useState<string | null>(null)
  const copyDirDraft = copyDir ?? savedCopyDir
  const [exporting, setExporting] = useState(false)

  async function browseForCopyDir() {
    try {
      const picked = await chooseFolder.mutateAsync({
        start: copyDirDraft.trim() || null,
        title: "Choose a folder to copy Waymark backups to",
      })
      if (picked) await saveCopyDir(picked)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not open the folder picker"))
    }
  }

  async function saveCopyDir(value: string) {
    try {
      await patchSettings.mutateAsync({ backup_copy_dir: value })
      setCopyDir(null)
      toast.success(value.trim() ? "Backups will also be copied to that folder" : "Backup copy folder turned off")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not use that folder"))
    }
  }

  async function openFolder() {
    try {
      await openDataFolder.mutateAsync()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not open the data folder"))
    }
  }

  async function backupNow() {
    try {
      const result = await runBackup.mutateAsync()
      if (result?.copy_error) toast.warning(`Backup written locally. ${result.copy_error}`)
      else if (result?.copied_to) toast.success("Backup written and copied to your backup folder")
      else toast.success("Backup written")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not run the backup"))
    }
  }

  async function exportJson() {
    setExporting(true)
    try {
      const res = await fetch("/api/export")
      if (!res.ok) throw new Error(`Export failed (${res.status})`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `waymark-export-${todayIso()}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success("Exported household data as JSON")
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not export data"))
    } finally {
      setExporting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Data</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {systemInfo && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-muted p-3 text-sm">
            <span className="text-ink-muted">
              Waymark <span className="text-ink">v{systemInfo.version}</span>
            </span>
            <span className="text-ink-muted">·</span>
            <span className="text-ink-muted">
              Data folder: <span className="font-mono text-ink">{systemInfo.data_dir}</span>
            </span>
            <Button
              onClick={openFolder}
              disabled={openDataFolder.isPending}
              variant="outline"
              size="sm"
              className="ml-auto w-fit"
            >
              Open folder
            </Button>
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="backup-copy-dir">Also copy backups to</Label>
          <div className="flex flex-wrap gap-2">
            <Input
              id="backup-copy-dir"
              className="min-w-0 flex-1 font-mono text-xs"
              placeholder="e.g. C:\Users\you\OneDrive\Waymark backups"
              value={copyDirDraft}
              onChange={(e) => setCopyDir(e.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              disabled={chooseFolder.isPending}
              onClick={browseForCopyDir}
            >
              {chooseFolder.isPending ? "Choosing…" : "Browse…"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-fit"
              disabled={patchSettings.isPending || copyDirDraft.trim() === savedCopyDir}
              onClick={() => saveCopyDir(copyDirDraft)}
            >
              Save
            </Button>
            {savedCopyDir && (
              <Button
                variant="ghost"
                size="sm"
                className="w-fit"
                disabled={patchSettings.isPending}
                onClick={() => saveCopyDir("")}
              >
                Turn off
              </Button>
            )}
          </div>
          <p className="text-xs text-ink-muted">
            Optional. Every backup (nightly, on close, and Backup now) is kept in the data folder and
            also copied here, e.g. a OneDrive folder so it syncs off this PC. Leave blank to turn off.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={backupNow} disabled={runBackup.isPending} className="w-fit">
            Backup now
          </Button>
          <Button
            onClick={exportJson}
            disabled={exporting}
            variant="outline"
            className="w-fit"
          >
            Export JSON
          </Button>
        </div>
        <div className="divide-y divide-border">
          {(backups ?? []).map((backup) => (
            <div key={backup.filename} className="flex items-center justify-between py-2 text-sm">
              <span className="text-ink">{backup.filename}</span>
              <span className="text-ink-muted">{formatDate(backup.created_at)}</span>
              <span className="text-ink-muted">{(backup.size_bytes / 1024).toFixed(0)} KB</span>
            </div>
          ))}
          {(backups ?? []).length === 0 && (
            <p className="py-2 text-sm text-ink-muted">No backups yet.</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

interface PersonRowProps {
  person: NonNullable<ReturnType<typeof usePeople>["data"]>[number]
  onUpdate: (payload: {
    date_of_birth?: string | null
    retirement_age?: number
    include_in_household?: boolean
  }) => void
}

function PersonRow({ person, onUpdate }: PersonRowProps) {
  const deletePerson = useDeletePerson()

  async function remove() {
    try {
      await deletePerson.mutateAsync(person.id)
      toast.success(`${person.name} deleted`)
    } catch (err) {
      // The backend refuses while they still own accounts — surface that message verbatim.
      toast.error(apiErrorMessage(err, "Could not delete this person"))
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3">
      <PersonAvatar name={person.name} color={person.color} />
      <span className="min-w-24 text-sm text-ink">{person.name}</span>

      <div className="flex flex-col gap-1">
        <Label className="text-xs">
          <HelpTip content={PERSON_HELP.dateOfBirth}>Date of birth</HelpTip>
        </Label>
        <DateInput
          value={person.date_of_birth ?? undefined}
          onChange={(v) => onUpdate({ date_of_birth: v ?? null })}
          className="h-8 w-36"
        />
      </div>

      <div className="flex flex-col gap-1">
        <Label className="text-xs">
          <HelpTip content={PERSON_HELP.retirementAge}>Retirement age</HelpTip>
        </Label>
        <Input
          type="number"
          className="h-8 w-20"
          value={person.retirement_age}
          onChange={(e) => onUpdate({ retirement_age: Number(e.target.value) })}
        />
      </div>

      <div className="flex flex-col items-center gap-1">
        <Label className="text-xs">
          <HelpTip content={PERSON_HELP.inHousehold}>In household</HelpTip>
        </Label>
        <Switch
          checked={person.include_in_household}
          onCheckedChange={(checked) => onUpdate({ include_in_household: checked })}
        />
      </div>

      <AlertDialog>
        <AlertDialogTrigger
          render={
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto text-ink-muted hover:text-loss"
              disabled={deletePerson.isPending}
            />
          }
        >
          Delete
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {person.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently removes this person. They can only be deleted once they no longer
              own any accounts.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
