import { useSyncExternalStore } from "react"

/** Which holdings the Live page shows: everything, only investment accounts (ISAs, general
 *  accounts: what a broker's app shows) or only pensions. Kept on this device, like the start
 *  page. Same module-level pub/sub pattern as lib/startPage.ts. */
export type LiveView = "all" | "investments" | "pensions"

const KEY = "nw:live-view"
const listeners = new Set<() => void>()

function readView(): LiveView {
  try {
    const stored = localStorage.getItem(KEY)
    return stored === "investments" || stored === "pensions" ? stored : "all"
  } catch {
    return "all"
  }
}

let view = readView()

export function setLiveView(value: LiveView): void {
  view = value
  try {
    localStorage.setItem(KEY, value)
  } catch {
    // localStorage unavailable: the choice lasts for this session only
  }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useLiveView(): LiveView {
  return useSyncExternalStore(subscribe, () => view)
}

export function isPension(account: { category: string }): boolean {
  return account.category === "pension"
}

/** The accounts a view shows. A view with nothing in it (the last pension was deleted, say)
 *  falls back to everything, so the page is never empty because of a remembered choice. */
export function accountsInView<T extends { category: string }>(accounts: T[], chosen: LiveView): { view: LiveView; accounts: T[] } {
  if (chosen !== "all") {
    const wanted = accounts.filter((a) => isPension(a) === (chosen === "pensions"))
    if (wanted.length > 0) return { view: chosen, accounts: wanted }
  }
  return { view: "all", accounts }
}

/** Whether there is a choice to offer: both kinds of account exist. */
export function hasBothKinds(accounts: { category: string }[]): boolean {
  return accounts.some(isPension) && accounts.some((a) => !isPension(a))
}
