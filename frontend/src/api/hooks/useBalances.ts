import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type BalanceEntryOut = components["schemas"]["BalanceEntryOut"]
export type BalanceEntryIn = components["schemas"]["BalanceEntryIn"]
export type QuickUpdateRow = components["schemas"]["QuickUpdateRow"]
export type BulkBalanceEntry = components["schemas"]["BulkBalanceEntry"]

function useInvalidateBalances() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["balances"] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account"] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
    queryClient.invalidateQueries({ queryKey: ["quick-update"] })
  }
}

export function useAccountBalances(accountId: number | undefined) {
  return useQuery({
    queryKey: ["balances", accountId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/balances", {
        params: { path: { account_id: accountId! } },
      })
      if (error) throw error
      return data
    },
    enabled: accountId !== undefined,
  })
}

export function useSaveBalance() {
  const invalidate = useInvalidateBalances()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: BalanceEntryIn }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/balances", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteBalance() {
  const invalidate = useInvalidateBalances()
  return useMutation({
    mutationFn: async (entryId: number) => {
      const { error } = await apiClient.DELETE("/api/balances/{entry_id}", {
        params: { path: { entry_id: entryId } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}

export function useQuickUpdateRows(personId?: number) {
  return useQuery({
    queryKey: ["quick-update", personId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/balances/quick-update", {
        params: { query: { person_id: personId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useBulkSaveBalances() {
  const invalidate = useInvalidateBalances()
  return useMutation({
    mutationFn: async (entries: BulkBalanceEntry[]) => {
      const { data, error } = await apiClient.POST("/api/balances/bulk", { body: { entries } })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}
