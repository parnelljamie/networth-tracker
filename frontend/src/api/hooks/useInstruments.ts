import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"
import { useRole } from "@/api/hooks/useSync"
import { useSyncAllTrading212 } from "@/api/hooks/useTrading212"

export type InstrumentOut = components["schemas"]["InstrumentOut"]
export type InstrumentCreate = components["schemas"]["InstrumentCreate"]
export type InstrumentSearchResultOut = components["schemas"]["InstrumentSearchResultOut"]
export type InstrumentUpdate = components["schemas"]["InstrumentUpdate"]

export function useInstruments() {
  return useQuery({
    queryKey: ["instruments", "list"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/instruments")
      if (error) throw error
      return data
    },
  })
}

/** The latest stored close on or before `date` (looking back up to two weeks, to cover weekends and
 * bank holidays), or null when none is stored. Reads the local price table only. */
export function useInstrumentPriceOn(instrumentId: number | undefined, date: string | undefined) {
  return useQuery({
    queryKey: ["instruments", "price-on", instrumentId, date],
    enabled: instrumentId !== undefined && !!date,
    queryFn: async () => {
      const to = new Date(`${date}T00:00:00Z`)
      const from = new Date(to.getTime() - 14 * 86_400_000).toISOString().slice(0, 10)
      const { data, error } = await apiClient.GET("/api/instruments/{instrument_id}/prices", {
        params: { path: { instrument_id: instrumentId! }, query: { date_from: from, date_to: date } },
      })
      if (error) throw error
      return data.length > 0 ? data[data.length - 1] : null
    },
  })
}

/** Changing a manual price or what it follows rebuilds history in the background, so values,
 * holdings and charts are refetched now and again once that's had a moment. */
export function useUpdateInstrument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: InstrumentUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/instruments/{instrument_id}", {
        params: { path: { instrument_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      const refresh = () => {
        for (const key of ["instruments", "holdings", "accounts", "account", "networth"]) {
          queryClient.invalidateQueries({ queryKey: [key] })
        }
      }
      refresh()
      setTimeout(refresh, 3000)
    },
  })
}

export function useInstrumentSearch(query: string) {
  return useQuery({
    queryKey: ["instruments", "search", query],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/instruments/search", {
        params: { query: { q: query } },
      })
      if (error) throw error
      return data
    },
    enabled: query.trim().length > 0,
    staleTime: 60_000,
  })
}

export function useCreateInstrument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: InstrumentCreate) => {
      const { data, error } = await apiClient.POST("/api/instruments", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instruments"] })
    },
  })
}

export function useRefreshPrices() {
  const queryClient = useQueryClient()
  const desktop = useRole() === "desktop"
  const syncTrading212 = useSyncAllTrading212()
  return useMutation({
    mutationFn: async (force: boolean) => {
      // Update prices also pulls new Trading 212 activity (PC only), in the background; holdings
      // changes pop up to accept when it lands (components/Trading212ChangesDialog.tsx).
      if (desktop) syncTrading212.mutate()
      const { data, error } = await apiClient.POST("/api/prices/refresh", {
        params: { query: { force } },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] })
      queryClient.invalidateQueries({ queryKey: ["account"] })
      queryClient.invalidateQueries({ queryKey: ["holdings"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
      queryClient.invalidateQueries({ queryKey: ["prices", "status"] })
    },
  })
}

export function usePricesStatus() {
  return useQuery({
    queryKey: ["prices", "status"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/prices/status", {})
      if (error) throw error
      return data
    },
    refetchInterval: 60_000,
  })
}
