import { HorizonToggle, type HorizonYears } from "@/components/HorizonToggle"
import { RangeFilter } from "@/components/RangeFilter"
import type { ChartRange } from "@/lib/dates"

const HISTORY_RANGES: ChartRange[] = ["1W", "1M", "3M", "6M", "1Y", "All"]

interface HistoryProjectionControlsProps {
  range: ChartRange
  onRangeChange: (range: ChartRange) => void
  showProjection: boolean
  onShowProjectionChange: (show: boolean) => void
  horizon: HorizonYears
  onHorizonChange: (years: HorizonYears) => void
}

/** Range buttons, a Show projection toggle and (when shown) the projection horizon, for
 *  CurrentVsProjectedChart headers. */
export function HistoryProjectionControls({
  range,
  onRangeChange,
  showProjection,
  onShowProjectionChange,
  horizon,
  onHorizonChange,
}: HistoryProjectionControlsProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <RangeFilter value={range} onChange={onRangeChange} ranges={HISTORY_RANGES} />
      <label className="flex items-center gap-2 text-[13px] text-ink-2">
        <input
          type="checkbox"
          className="size-4 accent-(--accent)"
          checked={showProjection}
          onChange={(e) => onShowProjectionChange(e.target.checked)}
        />
        Show projection
      </label>
      {showProjection && <HorizonToggle value={horizon} onChange={onHorizonChange} />}
    </div>
  )
}
