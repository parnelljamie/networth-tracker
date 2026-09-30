import { useSyncExternalStore } from "react"

// Same module-level pub/sub pattern as lib/commandPalette.ts. Which Trading 212 syncs the user
// has put off ("Not now") this session, by pending batch id. Not persisted: anything still
// waiting pops up again next time the app opens.
let dismissed: ReadonlySet<number> = new Set()
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

export function dismissTrading212Changes(batchId: number): void {
  dismissed = new Set([...dismissed, batchId])
  emit()
}

/** Settings / the account page's "Review changes": bring the popup back. */
export function showTrading212Changes(batchId: number): void {
  dismissed = new Set([...dismissed].filter((id) => id !== batchId))
  emit()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): ReadonlySet<number> {
  return dismissed
}

export function useDismissedTrading212Changes(): ReadonlySet<number> {
  return useSyncExternalStore(subscribe, getSnapshot)
}
