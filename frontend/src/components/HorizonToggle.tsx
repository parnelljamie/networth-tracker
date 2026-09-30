import { Segmented } from "@/components/Segmented"

export const HORIZON_YEARS = [5, 10, 20, 30] as const
export type HorizonYears = (typeof HORIZON_YEARS)[number]

/** Projection horizon control for the category pages' current-vs-projected charts. */
export function HorizonToggle({
  value,
  onChange,
}: {
  value: HorizonYears
  onChange: (value: HorizonYears) => void
}) {
  return (
    <Segmented
      label="Projection horizon"
      options={HORIZON_YEARS.map((years) => ({ value: years, label: `${years}y` }))}
      value={value}
      onChange={onChange}
      size="sm"
    />
  )
}
