import { useState } from "react"
import { toast } from "sonner"
import type { AccountDetail } from "@/api/hooks/useAccounts"
import { useUpdateAccount } from "@/api/hooks/useAccounts"
import { usePeople } from "@/api/hooks/usePeople"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { OwnersEditor, type OwnerShareValue } from "@/components/OwnersEditor"
import { PercentInput } from "@/components/PercentInput"
import { apiErrorMessage } from "@/lib/api-error"

const SINGLE_OWNER_WRAPPERS = new Set(["isa", "lisa", "jisa", "sipp", "workplace_pension", "db_pension"])

interface AccountSettingsFormProps {
  account: AccountDetail
  /** Called after a successful save (e.g. to close a dialog). */
  onSaved?: () => void
  className?: string
}

/**
 * The account edit form (name, provider, owners, expected return, fee, include-in-net-worth,
 * liquidity). Shared between AccountDetail's Settings tab and the lightweight inline edit
 * dialog opened from the Person page's account list, so both stay in sync.
 */
export function AccountSettingsForm({ account, onSaved, className }: AccountSettingsFormProps) {
  const { data: people } = usePeople()
  const updateAccount = useUpdateAccount()

  const [name, setName] = useState(account.name)
  const [provider, setProvider] = useState(account.provider ?? "")
  const [owners, setOwners] = useState<OwnerShareValue[]>(
    account.owners.map((o) => ({ personId: o.person_id, share: o.share }))
  )
  const [expectedReturn, setExpectedReturn] = useState<number | undefined>(
    account.expected_return_rate ?? undefined
  )
  const [annualFee, setAnnualFee] = useState<number | undefined>(account.annual_fee_rate)
  const [includeInNetworth, setIncludeInNetworth] = useState(account.include_in_networth)
  const [isLiquid, setIsLiquid] = useState(account.is_liquid)

  const singleOwner = SINGLE_OWNER_WRAPPERS.has(account.wrapper)
  const shareTotal = owners.reduce((sum, o) => sum + o.share, 0)
  const ownersValid = owners.length > 0 && (singleOwner || Math.abs(shareTotal - 1) < 1e-6)

  async function save() {
    try {
      await updateAccount.mutateAsync({
        id: account.id,
        payload: {
          name,
          provider: provider || null,
          owners: owners.map((o) => ({ person_id: o.personId, share: o.share })),
          expected_return_rate: expectedReturn ?? null,
          annual_fee_rate: annualFee,
          include_in_networth: includeInNetworth,
          is_liquid: isLiquid,
        },
      })
      toast.success("Account updated")
      onSaved?.()
    } catch (err) {
      toast.error(apiErrorMessage(err, "Could not update the account"))
    }
  }

  return (
    <div className={className ?? "flex flex-col gap-4"}>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`settings-name-${account.id}`}>Name</Label>
        <Input id={`settings-name-${account.id}`} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`settings-provider-${account.id}`}>Provider</Label>
        <Input
          id={`settings-provider-${account.id}`}
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        />
      </div>

      <OwnersEditor
        people={people ?? []}
        value={owners}
        onChange={setOwners}
        singleOwner={singleOwner}
      />

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Expected return</Label>
          <PercentInput value={expectedReturn} onChange={setExpectedReturn} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>Annual fee</Label>
          <PercentInput value={annualFee} onChange={setAnnualFee} />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <Label htmlFor={`include-networth-${account.id}`}>Include in net worth</Label>
        <Switch
          id={`include-networth-${account.id}`}
          checked={includeInNetworth}
          onCheckedChange={setIncludeInNetworth}
        />
      </div>
      <div className="flex items-center justify-between">
        <Label htmlFor={`is-liquid-${account.id}`}>Liquid</Label>
        <Switch id={`is-liquid-${account.id}`} checked={isLiquid} onCheckedChange={setIsLiquid} />
      </div>

      <Button onClick={save} disabled={!ownersValid || updateAccount.isPending} className="w-fit">
        Save changes
      </Button>
    </div>
  )
}
