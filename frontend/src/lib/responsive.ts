import { useSyncExternalStore } from "react"

// Matches Tailwind's `md` breakpoint: below it the app uses its phone layout (docs/07-mobile.md).
const PHONE_QUERY = "(max-width: 767px)"

function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(PHONE_QUERY)
  mql.addEventListener("change", onChange)
  return () => mql.removeEventListener("change", onChange)
}

/** True below the `md` breakpoint. For layout that CSS classes can't express, such as chart ticks. */
export function useIsPhone(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(PHONE_QUERY).matches, () => false)
}

/** Date ticks per time axis: fewer on a phone so the dates and the age rows under them don't collide. */
export function useTimeTickCount(): number {
  return useIsPhone() ? 3 : 5
}
