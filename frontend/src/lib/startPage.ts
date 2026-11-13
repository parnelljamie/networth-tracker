import { useSyncExternalStore } from "react"

/** Which page the app opens on. Kept on this device (like the theme), so the phone and the PC
 *  can differ. Same module-level pub/sub pattern as lib/theme.ts. */
export type StartPage = "overview" | "live" | "last"

const PREF_KEY = "nw:start-page"
const LAST_PATH_KEY = "nw:last-path"
const listeners = new Set<() => void>()

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // localStorage unavailable: the choice lasts for this session only
  }
}

function readPreference(): StartPage {
  const stored = read(PREF_KEY)
  return stored === "live" || stored === "last" ? stored : "overview"
}

let preference = readPreference()

export function setStartPage(value: StartPage): void {
  preference = value
  write(PREF_KEY, value)
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useStartPage(): StartPage {
  return useSyncExternalStore(subscribe, () => preference)
}

/** Remember where the user is, for "where I left off". */
export function rememberPath(path: string): void {
  write(LAST_PATH_KEY, path)
}

/** Where to go instead of the Overview when the app opens at "/", or null to stay. */
export function startPath(pref: StartPage = preference, lastPath: string | null = read(LAST_PATH_KEY)): string | null {
  if (pref === "live") return "/live"
  if (pref === "last" && lastPath && lastPath.startsWith("/") && lastPath !== "/") return lastPath
  return null
}
