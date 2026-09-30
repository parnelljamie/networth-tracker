import { useSyncExternalStore } from "react"

type ThemePreference = "light" | "dark" | "system"
type ResolvedTheme = "light" | "dark"

const STORAGE_KEY = "nw:theme"
const listeners = new Set<() => void>()
const media = window.matchMedia?.("(prefers-color-scheme: dark)")

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "light" || stored === "dark") return stored
  } catch {
    // ignore
  }
  return "system"
}

function resolve(pref: ThemePreference): ResolvedTheme {
  if (pref === "system") return media?.matches ? "dark" : "light"
  return pref
}

let preference = readStoredPreference()
let resolved = resolve(preference)

function apply(): void {
  document.documentElement.setAttribute("data-theme", resolved)
}
apply()

media?.addEventListener("change", () => {
  if (preference !== "system") return
  resolved = resolve(preference)
  apply()
  emit()
})

function emit(): void {
  for (const listener of listeners) listener()
}

export function setTheme(pref: ThemePreference): void {
  preference = pref
  resolved = resolve(pref)
  try {
    if (pref === "system") localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, pref)
  } catch {
    // ignore
  }
  apply()
  emit()
}

export function toggleTheme(): void {
  setTheme(resolved === "dark" ? "light" : "dark")
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): ResolvedTheme {
  return resolved
}

export function useTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, getSnapshot)
}
