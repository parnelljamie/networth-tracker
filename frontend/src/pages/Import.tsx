import { useState } from "react"
import { toast } from "sonner"
import { useAccounts } from "@/api/hooks/useAccounts"
import {
  type ImportBatchOut,
  type ImportKind,
  type PreviewOut,
  useCommitImport,
  useImportBatches,
  useImportJobStatus,
  usePreviewImport,
  useRollbackImport,
  useUploadImport,
} from "@/api/hooks/useImports"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/PageHeader"
import { DateInput } from "@/components/DateInput"
import { EmptyState } from "@/components/EmptyState"
import { MatchImportInstruments } from "@/components/MatchImportInstruments"
import { Money } from "@/components/Money"
import { MoneyInput } from "@/components/MoneyInput"
import { Label } from "@/components/ui/label"
import { apiErrorMessage } from "@/lib/api-error"
import { formatDate } from "@/lib/dates"

// services/trading212_service.py PROFILE
const TRADING212_PROFILE = "Trading 212 API"

const KINDS: { value: ImportKind; label: string; hint: string }[] = [
  {
    value: "transactions",
    label: "Transaction history",
    hint: "A canonical CSV of buys, sells, deposits, dividends etc. for an ISA/GIA/SIPP",
  },
  {
    value: "balances",
    label: "Bank / balance statement",
    hint: "A bank CSV — a running balance column, or amounts plus a balance you enter for the latest date",
  },
]

/** docs/06-imports-future.md + docs/05-ui.md "Import `/import`": wizard (Upload -> Profile &
 * column mapping -> Instrument matching -> Preview & reconciliation -> Commit -> Rebuild
 * progress) plus an import history list with Undo. Column mapping and instrument-matching are
 * skipped automatically when the file's headers already match the canonical format (see
 * services/importers — most exports from this app's own canonical CSV need no mapping at all);
 * the wizard still surfaces unmatched instruments before letting you commit. */
export function Import() {
  const { data: accounts } = useAccounts()
  const { data: batches, isLoading: batchesLoading } = useImportBatches()

  const [kind, setKind] = useState<ImportKind>("transactions")
  const [accountId, setAccountId] = useState<number | undefined>(undefined)
  const [file, setFile] = useState<File | null>(null)
  const [batch, setBatch] = useState<ImportBatchOut | null>(null)
  const [headers, setHeaders] = useState<string[]>([])
  const [preview, setPreview] = useState<PreviewOut | null>(null)
  const [anchorBalance, setAnchorBalance] = useState<number | undefined>(undefined)
  const [anchorDate, setAnchorDate] = useState<string | undefined>(undefined)
  const [replaceStandIns, setReplaceStandIns] = useState(true)
  const [alignToCurrent, setAlignToCurrent] = useState(false)
  const [jobId, setJobId] = useState<string | undefined>(undefined)

  const upload = useUploadImport()
  const runPreview = usePreviewImport()
  const commit = useCommitImport()
  const rollback = useRollbackImport()
  const job = useImportJobStatus(jobId, jobId !== undefined)

  function openBatch(b: ImportBatchOut) {
    resetWizard()
    setKind(b.kind)
    setAccountId(b.account_id)
    setBatch(b)
  }

  function resetWizard() {
    setFile(null)
    setBatch(null)
    setHeaders([])
    setPreview(null)
    setAnchorBalance(undefined)
    setAnchorDate(undefined)
    setJobId(undefined)
  }

  async function doUpload() {
    if (!accountId || !file) return
    try {
      const result = await upload.mutateAsync({ kind, accountId, file })
      if (!result) return
      setBatch(result.batch)
      setHeaders(result.headers)
      toast.success(`${file.name} uploaded — ${result.batch.rows_total || result.sample_rows.length} rows detected`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not upload that file"))
    }
  }

  async function doPreview() {
    if (!batch) return
    try {
      const result = await runPreview.mutateAsync({
        batchId: batch.id,
        payload: { anchor_balance_gbp: anchorBalance ?? null, anchor_date: anchorDate ?? null },
      })
      if (!result) return
      setPreview(result)
      setBatch(result.batch)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not preview that import"))
    }
  }

  async function doCommit() {
    if (!batch) return
    try {
      const result = await commit.mutateAsync({
        batchId: batch.id,
        payload: {
          replace_stand_ins: replaceStandIns,
          align_to_current: alignToCurrent,
          anchor_balance_gbp: anchorBalance ?? null,
          anchor_date: anchorDate ?? null,
        },
      })
      if (!result) return
      setBatch(result.batch)
      setJobId(result.job_id ?? undefined)
      toast.success(`Imported ${result.batch.rows_imported} rows`)
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not commit that import"))
    }
  }

  async function doRollback(id: number, filename: string) {
    try {
      await rollback.mutateAsync(id)
      toast.success(`${filename} undone — holdings and history restored`)
      if (batch?.id === id) resetWizard()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not undo that import"))
    }
  }

  const needsAnchor = kind === "balances" && preview !== null && !preview.ready && preview.reconciliation.length === 0
  const canCommit = preview !== null && preview.ready && batch?.status !== "committed"

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        eyebrow="Bring in history"
        title="Import"
        description="Bring in a platform’s full transaction history or a bank statement CSV. Nothing is written until you review the reconciliation and commit — every import can be undone."
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>1. Upload</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="import-kind">Kind</Label>
              <select
                id="import-kind"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as ImportKind)
                  resetWizard()
                }}
                className="h-9 rounded-md border border-border bg-card px-2 text-sm text-ink"
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="import-account">Account</Label>
              <select
                id="import-account"
                value={accountId ?? ""}
                onChange={(e) => {
                  setAccountId(e.target.value ? Number(e.target.value) : undefined)
                  resetWizard()
                }}
                className="h-9 min-w-48 rounded-md border border-border bg-card px-2 text-sm text-ink"
              >
                <option value="">Select…</option>
                {(accounts ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="import-file">CSV file</Label>
              <input
                id="import-file"
                type="file"
                accept=".csv"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm text-ink"
              />
            </div>
            <Button onClick={doUpload} disabled={!accountId || !file || upload.isPending}>
              Upload
            </Button>
          </div>
          <p className="text-xs text-ink-muted">
            {KINDS.find((k) => k.value === kind)?.hint}
          </p>
          {headers.length > 0 && (
            <p className="text-xs text-ink-muted">
              Detected columns: <span className="font-mono-figures">{headers.join(", ")}</span>
              {batch?.profile_name ? ` — matched saved profile "${batch.profile_name}"` : ""}
            </p>
          )}
        </CardContent>
      </Card>

      {batch && (
        <Card className="max-w-3xl">
          <CardHeader>
            <CardTitle>2. Preview &amp; reconciliation</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {kind === "balances" && (
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="anchor-balance">Balance on the latest date (if no running balance column)</Label>
                  <MoneyInput id="anchor-balance" value={anchorBalance} onChange={setAnchorBalance} className="w-32" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="anchor-date">Latest date</Label>
                  <DateInput id="anchor-date" value={anchorDate} onChange={setAnchorDate} className="w-40" />
                </div>
              </div>
            )}
            <Button onClick={doPreview} disabled={runPreview.isPending} className="w-fit">
              Run preview
            </Button>

            {needsAnchor && (
              <p className="text-sm text-warn">
                This file has no running balance column — enter the balance on its latest date above,
                then run the preview again.
              </p>
            )}

            {preview && (
              <div className="flex flex-col gap-3">
                {preview.row_errors.length > 0 && (
                  <p className="text-sm text-warn">
                    {preview.row_errors.length} row(s) could not be read (e.g. row{" "}
                    {preview.row_errors[0].row}: {preview.row_errors[0].message})
                  </p>
                )}
                {preview.ledger_warnings.length > 0 && (
                  <p className="text-sm text-warn">
                    {preview.ledger_warnings.length} ledger warning(s) — e.g. selling more than is
                    held usually means earlier history is still missing.
                  </p>
                )}
                {preview.unmatched_instruments.length > 0 && batch && (
                  <MatchImportInstruments
                    batchId={batch.id}
                    unmatched={preview.unmatched_instruments}
                    onResolved={() => void doPreview()}
                  />
                )}

                {preview.reconciliation.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-ink-muted">
                        <th className="py-1 pr-3">Instrument</th>
                        <th className="py-1 pr-3">Current units</th>
                        <th className="py-1 pr-3">Imported units</th>
                        <th className="py-1 pr-3">Current avg cost</th>
                        <th className="py-1 pr-3">Imported avg cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.reconciliation.map((row, i) => (
                        <tr key={row.instrument_id ?? i} className="border-t border-border">
                          <td className="py-1 pr-3">{row.symbol ?? row.name ?? "Cash"}</td>
                          <td className="py-1 pr-3 font-mono-figures">{row.current_units}</td>
                          <td className="py-1 pr-3 font-mono-figures">{row.imported_units}</td>
                          <td className="py-1 pr-3">
                            <Money value={row.current_avg_cost_gbp} />
                          </td>
                          <td className="py-1 pr-3">
                            <Money value={row.imported_avg_cost_gbp} />
                            {Math.abs(row.units_diff) > 1e-6 || Math.abs(row.avg_cost_diff_gbp) > 0.005 ? (
                              <span className="ml-1 text-warn"> ⚠ differs</span>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {preview && (
        <Card className="max-w-3xl">
          <CardHeader>
            <CardTitle>3. Commit</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {kind === "transactions" && (
              <div className="flex flex-col gap-2 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={replaceStandIns}
                    onChange={(e) => setReplaceStandIns(e.target.checked)}
                  />
                  Replace quick-entry opening balances / adjustments for instruments in this file
                  with the imported history (recommended)
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={alignToCurrent}
                    onChange={(e) => setAlignToCurrent(e.target.checked)}
                  />
                  Add a top-up adjustment today so positions still match what you hold now
                  (use this if the file is a partial export)
                </label>
              </div>
            )}
            <Button onClick={doCommit} disabled={!canCommit || commit.isPending} className="w-fit">
              Commit import
            </Button>

            {jobId && job.data && (
              <p className="text-xs text-ink-muted">
                Rebuilding history…{" "}
                {job.data.status === "done"
                  ? "done."
                  : job.data.status === "error"
                    ? `failed: ${job.data.error}`
                    : `${Math.round(job.data.progress * 100)}%`}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>Import history</CardTitle>
        </CardHeader>
        <CardContent>
          {!batchesLoading && (batches ?? []).length === 0 && (
            <EmptyState title="No imports yet" description="Uploaded files will show up here, with an Undo option after committing." />
          )}
          {(batches ?? []).length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-ink-muted">
                  <th className="py-1 pr-3">File</th>
                  <th className="py-1 pr-3">Kind</th>
                  <th className="py-1 pr-3">Imported</th>
                  <th className="py-1 pr-3">Skipped</th>
                  <th className="py-1 pr-3">Date</th>
                  <th className="py-1 pr-3">Status</th>
                  <th className="py-1 pr-3" />
                </tr>
              </thead>
              <tbody>
                {(batches ?? []).map((b) => (
                  <tr key={b.id} className="border-t border-border">
                    <td className="py-1 pr-3">{b.filename}</td>
                    <td className="py-1 pr-3">{b.kind}</td>
                    <td className="py-1 pr-3 font-mono-figures">{b.rows_imported}</td>
                    <td className="py-1 pr-3 font-mono-figures">{b.rows_skipped}</td>
                    <td className="py-1 pr-3">{b.imported_at ? formatDate(b.imported_at) : "—"}</td>
                    <td className="py-1 pr-3">{b.status}</td>
                    <td className="py-1 pr-3">
                      {/* Trading 212 syncs waiting to be accepted live in their own popup. */}
                      {(b.status === "pending" || b.status === "previewed") &&
                        b.profile_name !== TRADING212_PROFILE &&
                        batch?.id !== b.id && (
                        <Button variant="ghost" size="sm" onClick={() => openBatch(b)}>
                          Review
                        </Button>
                      )}
                      {b.status === "committed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => doRollback(b.id, b.filename)}
                          disabled={rollback.isPending}
                        >
                          Undo
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
