import { useSyncExternalStore } from "react"

const STORAGE_KEY = "nw:privacy"
const listeners = new Set<() => void>()

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1"
  } catch {
    return false
  }
}

let privacyMode = readStored()

function emit(): void {
  for (const listener of listeners) listener()
}

export function setPrivacyMode(value: boolean): void {
  privacyMode = value
  try {
    localStorage.setItem(STORAGE_KEY, value ? "1" : "0")
  } catch {
    // localStorage unavailable (private window, etc.) — in-memory only
  }
  emit()
}

export function togglePrivacyMode(): void {
  setPrivacyMode(!privacyMode)
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): boolean {
  return privacyMode
}

export function usePrivacyMode(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot)
}
