import { useAccount } from "@/api/hooks/useAccounts"
import { AccountSettingsForm } from "@/components/AccountSettingsForm"
import { StalenessBadge } from "@/components/StalenessBadge"
import { useRole } from "@/api/hooks/useSync"
import { Trading212Card } from "@/components/account/Trading212Card"

export function SettingsTab({ account }: { account: NonNullable<ReturnType<typeof useAccount>["data"]> }) {
  const role = useRole()
  return (
    <div className="flex max-w-md flex-col gap-4">
      <AccountSettingsForm account={account} />
      <StalenessBadge
        staleness={account.staleness as "ok" | "warn" | "alert"}
        daysSince={account.days_since_update ?? null}
        prices={account.valuation_method === "holdings"}
        className="text-xs"
      />
      {/* Syncing talks to Trading 212 from the PC; the phone gets the results by its own sync. */}
      {account.valuation_method === "holdings" && role !== "phone" && <Trading212Card accountId={account.id} />}
    </div>
  )
}
