import type { Trading212LinkOut } from "@/api/hooks/useTrading212"
import { timeAgo } from "@/lib/dates"

const STATUS_TEXT: Record<string, string> = {
  idle: "Not synced yet",
  running: "Syncing…",
  synced: "Up to date",
  up_to_date: "Up to date",
  needs_review: "Changes waiting for you to accept",
  error: "Sync failed",
}

/** "Up to date · last checked 5 min ago · 2 new transactions" */
export function trading212StatusLine(link: Trading212LinkOut): string {
  const parts = [STATUS_TEXT[link.status] ?? link.status]
  if (link.last_synced_at && link.status !== "running") {
    parts.push(`last checked ${timeAgo(link.last_synced_at)}`)
  }
  if (link.status === "synced" && link.last_new_rows > 0) {
    parts.push(`${link.last_new_rows} new transaction${link.last_new_rows === 1 ? "" : "s"}`)
  }
  return parts.join(" · ")
}
