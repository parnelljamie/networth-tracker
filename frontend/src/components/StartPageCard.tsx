import { Segmented } from "@/components/Segmented"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { setStartPage, useStartPage, type StartPage } from "@/lib/startPage"

const OPTIONS: { value: StartPage; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "live", label: "Live" },
  { value: "last", label: "Where I left off" },
]

/** Settings: which page Waymark opens on. Saved on this device only. */
export function StartPageCard() {
  const startPage = useStartPage()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Start page</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-ink-muted">
          The page Waymark shows when it opens. Choose Live to go straight to your shares and funds.
        </p>
        <Segmented options={OPTIONS} value={startPage} onChange={setStartPage} label="Open Waymark on" />
        <p className="text-xs text-ink-muted">Saved on this device, so your phone and PC can differ.</p>
      </CardContent>
    </Card>
  )
}
