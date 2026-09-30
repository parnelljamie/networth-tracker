import { useSyncExternalStore } from "react"

// Same module-level pub/sub pattern as lib/privacy.ts / lib/theme.ts / lib/appDialogs.ts.
// Not persisted — open state always starts closed.
let open = false
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

export function openCommandPalette(): void {
  open = true
  emit()
}

export function closeCommandPalette(): void {
  open = false
  emit()
}

export function toggleCommandPalette(): void {
  open = !open
  emit()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): boolean {
  return open
}

export function useCommandPaletteOpen(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot)
}
