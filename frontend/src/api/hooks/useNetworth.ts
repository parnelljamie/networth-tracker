import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type NetWorthCurrent = components["schemas"]["NetWorthCurrent"]
export type NetWorthHistory = components["schemas"]["NetWorthHistory"]

export function useNetWorthCurrent(personId?: number) {
  return useQuery({
    queryKey: ["networth", "current", personId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/networth/current", {
        params: { query: { person_id: personId } },
      })
      if (error) throw error
      return data
    },
    refetchInterval: 5 * 60_000,
  })
}

export function useNetWorthHistory(params: {
  personId?: number
  dateFrom?: string
  dateTo?: string
  granularity?: "day" | "week" | "month"
  groupBy?: "category" | "account" | "person"
}) {
  return useQuery({
    queryKey: ["networth", "history", params],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/networth/history", {
        params: {
          query: {
            person_id: params.personId,
            date_from: params.dateFrom,
            date_to: params.dateTo,
            granularity: params.granularity ?? "day",
            group_by: params.groupBy ?? "category",
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}
