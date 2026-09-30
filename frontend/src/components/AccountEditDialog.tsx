import { useAccount } from "@/api/hooks/useAccounts"
import { AccountSettingsForm } from "@/components/AccountSettingsForm"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface AccountEditDialogProps {
  accountId: number | undefined
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Lightweight inline "Edit" affordance opened from the Person page's account list — the same
 * fields as AccountDetail's Settings tab (via the shared AccountSettingsForm), in a dialog so
 * the user doesn't have to navigate away just to rename an account, fix its owners/share, or
 * flip include-in-net-worth/liquid. Deeper editing (holdings, transactions, balances, plans,
 * mortgage schedule) still lives on the full account page.
 */
export function AccountEditDialog({ accountId, open, onOpenChange }: AccountEditDialogProps) {
  const { data: account } = useAccount(open ? accountId : undefined)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {account?.name ?? "account"}</DialogTitle>
        </DialogHeader>
        {account ? (
          <AccountSettingsForm account={account} onSaved={() => onOpenChange(false)} />
        ) : (
          <p className="text-sm text-ink-muted">Loading…</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
