import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { Person } from "@/api/hooks/usePeople"
import { PersonAvatar } from "@/components/PersonAvatar"

export interface OwnerShareValue {
  personId: number
  share: number
}

interface OwnersEditorProps {
  people: Person[]
  value: OwnerShareValue[]
  onChange: (value: OwnerShareValue[]) => void
  /** Wrapped accounts (ISA, SIPP, ...) must have exactly one owner at 100%. */
  singleOwner: boolean
}

export function OwnersEditor({ people, value, onChange, singleOwner }: OwnersEditorProps) {
  if (singleOwner) {
    return (
      <div className="flex flex-col gap-1.5">
        <Label>Owner</Label>
        <Select
          value={value[0]?.personId.toString() ?? ""}
          onValueChange={(personId) => onChange([{ personId: Number(personId), share: 1 }])}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Choose a person" />
          </SelectTrigger>
          <SelectContent>
            {people.map((p) => (
              <SelectItem key={p.id} value={p.id.toString()}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    )
  }

  const selectedIds = new Set(value.map((o) => o.personId))
  const total = value.reduce((sum, o) => sum + o.share, 0)

  // Adding or removing an owner re-splits evenly (one owner 100%, two 50/50, ...); the
  // percentages can still be edited by hand afterwards.
  function toggle(personId: number) {
    const next = selectedIds.has(personId)
      ? value.filter((o) => o.personId !== personId)
      : [...value, { personId, share: 0 }]
    onChange(evenSplit(next))
  }

  function setShare(personId: number, pct: number) {
    onChange(value.map((o) => (o.personId === personId ? { ...o, share: pct / 100 } : o)))
  }

  function splitEvenly() {
    if (value.length === 0) return
    onChange(evenSplit(value))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <Label>Owners</Label>
        {value.length === 2 && (
          <Button type="button" variant="ghost" size="sm" onClick={splitEvenly}>
            Joint 50/50
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-2">
        {people.map((person) => {
          const owner = value.find((o) => o.personId === person.id)
          return (
            <div key={person.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                className="size-4"
                checked={selectedIds.has(person.id)}
                onChange={() => toggle(person.id)}
                aria-label={`Include ${person.name} as an owner`}
              />
              <PersonAvatar name={person.name} color={person.color} size="sm" />
              <span className="flex-1 text-sm text-ink">{person.name}</span>
              {owner && (
                <div className="relative w-20">
                  <Input
                    type="number"
                    step="1"
                    min={0}
                    max={100}
                    className="pr-6 text-right tabular-nums"
                    value={Math.round(owner.share * 10000) / 100}
                    onChange={(e) => setShare(person.id, Number(e.target.value))}
                  />
                  <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-xs text-ink-muted">
                    %
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <p className={`text-xs ${Math.abs(total - 1) > 1e-6 ? "text-loss" : "text-ink-muted"}`}>
        Total: {Math.round(total * 10000) / 100}% {Math.abs(total - 1) > 1e-6 && "(must total 100%)"}
      </p>
    </div>
  )
}

/** Equal shares summing to exactly 100%; the first owner absorbs the rounding. */
function evenSplit(owners: OwnerShareValue[]): OwnerShareValue[] {
  if (owners.length === 0) return owners
  const even = Math.round((100 / owners.length) * 100) / 100
  return owners.map((o, i) => ({
    ...o,
    share: (i === 0 ? 100 - even * (owners.length - 1) : even) / 100,
  }))
}
