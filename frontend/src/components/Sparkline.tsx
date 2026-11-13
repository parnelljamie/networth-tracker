import { cn } from "@/lib/utils"

interface SparklineProps {
  values: number[]
  className?: string
  /** For screen readers, e.g. "Up over 30 days". */
  label?: string
}

const WIDTH = 96
const HEIGHT = 28
const PAD = 2

/** A small line of a price over time, coloured by whether it ends above or below its start. */
export function Sparkline({ values, className, label }: SparklineProps) {
  if (values.length < 2) return <span className={cn("inline-block", className)} style={{ width: WIDTH, height: HEIGHT }} />
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = (WIDTH - PAD * 2) / (values.length - 1)
  const points = values
    .map((v, i) => `${(PAD + i * step).toFixed(1)},${(HEIGHT - PAD - ((v - min) / span) * (HEIGHT - PAD * 2)).toFixed(1)}`)
    .join(" ")
  const last = values[values.length - 1]
  const tone = last > values[0] ? "text-gain" : last < values[0] ? "text-loss" : "text-ink-muted"
  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      width={WIDTH}
      height={HEIGHT}
      className={cn("inline-block shrink-0", tone, className)}
      role="img"
      aria-label={label ?? "Price trend"}
    >
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
