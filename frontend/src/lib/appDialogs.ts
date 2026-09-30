import { useSyncExternalStore } from "react"
import type { Category } from "@/lib/categories"

// Shared, module-level open/close state for dialogs that must be triggerable from more than one
// place (TopBar buttons, CommandPalette, Overview empty-state actions). Same localStorage-free
// pub/sub pattern as lib/privacy.ts and lib/theme.ts — no context provider needed.

export interface AddAccountDefaults {
  category?: Category
  wrapper?: string
}

interface DialogsSnapshot {
  addAccountOpen: boolean
  addAccountDefaults: AddAccountDefaults | undefined
  quickUpdateOpen: boolean
  syncReportOpen: boolean
}

let snapshot: DialogsSnapshot = {
  addAccountOpen: false,
  addAccountDefaults: undefined,
  quickUpdateOpen: false,
  syncReportOpen: false,
}

const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

function set(partial: Partial<DialogsSnapshot>): void {
  snapshot = { ...snapshot, ...partial }
  emit()
}

export function openAddAccount(defaults?: AddAccountDefaults): void {
  set({ addAccountOpen: true, addAccountDefaults: defaults })
}

export function setAddAccountOpen(open: boolean): void {
  set({ addAccountOpen: open, addAccountDefaults: open ? snapshot.addAccountDefaults : undefined })
}

export function openQuickUpdate(): void {
  set({ quickUpdateOpen: true })
}

export function setQuickUpdateOpen(open: boolean): void {
  set({ quickUpdateOpen: open })
}

export function setSyncReportOpen(open: boolean): void {
  set({ syncReportOpen: open })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useDialogsState(): DialogsSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot)
}
