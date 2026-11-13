import { useEffect } from "react"
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"
import { LIVE_REFETCH_MS } from "@/api/hooks/useHoldings"

export type Trading212LiveOut = components["schemas"]["Trading212LiveOut"]
export type InstrumentPriceOut = components["schemas"]["InstrumentPriceOut"]

/** How often the Live page asks Trading 212 for its current prices while it is open. The
 *  backend answers anything sooner than 10 seconds from its last result. */
const TRADING212_LIVE_MS = 20_000

/** While mounted (and `enabled`), keeps pulling each linked Trading 212 account's live prices
 *  into the app, then re-reads everything valued from them. Stops when the page is left or the
 *  window is hidden. The key is deliberately outside "trading212", so sync invalidations don't
 *  fire extra requests. */
export function useTrading212Live(enabled: boolean) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ["trading212-live"],
    enabled,
    queryFn: async () => {
      const { data, error } = await apiClient.POST("/api/trading212/live")
      if (error) throw error
      return data
    },
    refetchInterval: TRADING212_LIVE_MS,
    staleTime: TRADING212_LIVE_MS,
    retry: false,
  })

  const fetchedAt = query.dataUpdatedAt
  const priced = query.data?.some((r) => r.priced > 0) ?? false
  useEffect(() => {
    if (!priced) return
    for (const key of ["holdings", "accounts", "account", "networth", "prices"]) {
      queryClient.invalidateQueries({ queryKey: [key] })
    }
  }, [fetchedAt, priced, queryClient])

  return query
}

/** Daily closes for several instruments since `dateFrom` (the holdings table's sparklines). */
export function useInstrumentPrices(instrumentIds: number[], dateFrom: string) {
  return useQueries({
    queries: instrumentIds.map((id) => ({
      queryKey: ["instruments", id, "prices", dateFrom],
      queryFn: async () => {
        const { data, error } = await apiClient.GET("/api/instruments/{instrument_id}/prices", {
          params: { path: { instrument_id: id }, query: { date_from: dateFrom } },
        })
        if (error) throw error
        return data
      },
      staleTime: 15 * LIVE_REFETCH_MS,
    })),
  })
}
