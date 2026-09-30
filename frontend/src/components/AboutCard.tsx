import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

const REPO_URL = "https://github.com/parnelljamie/networth-tracker"
const DONATE_URL = "https://buymeacoffee.com/jparnell"

/** Settings -> About: licence, the not-financial-advice disclaimer, and where the project lives. */
export function AboutCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>About</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm text-ink-muted">
        <p>
          Waymark is free, open-source software, released under the MIT licence. It keeps everything on your own devices
          and has no account, adverts or tracking.
        </p>
        <p>
          <span className="text-ink">Not financial advice.</span> Waymark is a record-keeping and estimation tool.
          Valuations, projections, allowances and tax figures are estimates based on what you enter, the assumptions you
          choose and third-party price data, and may be wrong or out of date. Don't rely on them alone for decisions about
          investments, pensions, tax or borrowing; speak to a regulated financial adviser for that. The software is
          provided as is, without warranty of any kind.
        </p>
        <div className="flex flex-wrap gap-2">
          <a href={REPO_URL} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Source code and issues
          </a>
          <a href={DONATE_URL} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Buy me a coffee
          </a>
        </div>
      </CardContent>
    </Card>
  )
}
