import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type AttributionOut = components["schemas"]["AttributionOut"]
export type DepositProtectionOut = components["schemas"]["DepositProtectionOut"]
export type XirrOut = components["schemas"]["XirrOut"]

export function useAttribution(params: { start: string; end: string; personId?: number }) {
  return useQuery({
    queryKey: ["insights", "attribution", params.start, params.end, params.personId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/insights/attribution", {
        params: { query: { start: params.start, end: params.end, person_id: params.personId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useDepositProtection() {
  return useQuery({
    queryKey: ["insights", "deposit-protection"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/insights/deposit-protection", {})
      if (error) throw error
      return data
    },
  })
}

export function useAccountXirr(accountId: number | undefined) {
  return useQuery({
    queryKey: ["insights", "xirr", accountId ?? null],
    enabled: accountId !== undefined,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/xirr", {
        params: { path: { account_id: accountId as number } },
      })
      if (error) throw error
      return data
    },
  })
}
