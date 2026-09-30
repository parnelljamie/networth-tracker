import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type Holdings = components["schemas"]["Holdings"]
export type HoldingPosition = components["schemas"]["HoldingPosition"]

async function fetchHoldings(accountId: number) {
  const { data, error } = await apiClient.GET("/api/accounts/{account_id}/holdings", {
    params: { path: { account_id: accountId } },
  })
  if (error) throw error
  return data
}

/** Holdings for several accounts at once, for views that aggregate the same instrument across
 *  accounts (the household Investments page). Query keys match `useHoldings`, so the cache is
 *  shared with the single-account account page. */
export function useHoldingsForAccounts(accountIds: number[]) {
  return useQueries({
    queries: accountIds.map((accountId) => ({
      queryKey: ["holdings", accountId],
      queryFn: () => fetchHoldings(accountId),
    })),
  })
}

function useInvalidateHoldings() {
  const queryClient = useQueryClient()
  return (accountId: number) => {
    queryClient.invalidateQueries({ queryKey: ["holdings", accountId] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account", accountId] })
    queryClient.invalidateQueries({ queryKey: ["transactions", accountId] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
  }
}

export function useHoldings(accountId: number | undefined) {
  return useQuery({
    queryKey: ["holdings", accountId],
    queryFn: () => fetchHoldings(accountId!),
    enabled: accountId !== undefined,
  })
}

export function useSetHolding() {
  const invalidate = useInvalidateHoldings()
  return useMutation({
    mutationFn: async ({
      accountId,
      instrumentId,
      units,
      avgCostGbp,
    }: {
      accountId: number
      instrumentId: number
      units: number
      avgCostGbp: number
    }) => {
      const { data, error } = await apiClient.PUT("/api/accounts/{account_id}/holdings/{instrument_id}", {
        params: { path: { account_id: accountId, instrument_id: instrumentId } },
        body: { units, avg_cost_gbp: avgCostGbp },
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, variables) => invalidate(variables.accountId),
  })
}

export function useDeleteHolding() {
  const invalidate = useInvalidateHoldings()
  return useMutation({
    mutationFn: async ({ accountId, instrumentId }: { accountId: number; instrumentId: number }) => {
      const { data, error } = await apiClient.DELETE(
        "/api/accounts/{account_id}/holdings/{instrument_id}",
        { params: { path: { account_id: accountId, instrument_id: instrumentId } } }
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, variables) => invalidate(variables.accountId),
  })
}

export function useSetCash() {
  const invalidate = useInvalidateHoldings()
  return useMutation({
    mutationFn: async ({ accountId, cashGbp }: { accountId: number; cashGbp: number }) => {
      const { data, error } = await apiClient.PUT("/api/accounts/{account_id}/cash", {
        params: { path: { account_id: accountId } },
        body: { cash_gbp: cashGbp },
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, variables) => invalidate(variables.accountId),
  })
}
