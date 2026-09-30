import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type TransactionOut = components["schemas"]["TransactionOut"]
export type TransactionCreate = components["schemas"]["TransactionCreate"]
export type ConfirmItem = components["schemas"]["ConfirmItem"]

function useInvalidateTransactions() {
  const queryClient = useQueryClient()
  return (accountId: number) => {
    queryClient.invalidateQueries({ queryKey: ["transactions", accountId] })
    queryClient.invalidateQueries({ queryKey: ["holdings", accountId] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account", accountId] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
  }
}

export function useTransactions(
  accountId: number | undefined,
  filters: { limit?: number; offset?: number } = {}
) {
  return useQuery({
    queryKey: ["transactions", accountId, filters],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/transactions", {
        params: {
          path: { account_id: accountId! },
          query: { limit: filters.limit ?? 100, offset: filters.offset ?? 0 },
        },
      })
      if (error) throw error
      return data
    },
    enabled: accountId !== undefined,
  })
}

export function useCreateTransaction() {
  const invalidate = useInvalidateTransactions()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: TransactionCreate }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/transactions", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, variables) => invalidate(variables.accountId),
  })
}

export function usePendingTransactions() {
  return useQuery({
    queryKey: ["transactions", "pending"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/transactions/pending", {})
      if (error) throw error
      return data
    },
    refetchInterval: 60_000,
  })
}

export function useConfirmTransactions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (items: ConfirmItem[]) => {
      const { data, error } = await apiClient.POST("/api/transactions/confirm", { body: { items } })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] })
      queryClient.invalidateQueries({ queryKey: ["holdings"] })
      queryClient.invalidateQueries({ queryKey: ["accounts"] })
      queryClient.invalidateQueries({ queryKey: ["account"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
      queryClient.invalidateQueries({ queryKey: ["allowances"] })
    },
  })
}

export function useDeleteTransaction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (txnId: number) => {
      const { error } = await apiClient.DELETE("/api/transactions/{txn_id}", {
        params: { path: { txn_id: txnId } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      // The account isn't known here; broadly invalidate holdings/transactions/networth.
      queryClient.invalidateQueries({ queryKey: ["transactions"] })
      queryClient.invalidateQueries({ queryKey: ["holdings"] })
      queryClient.invalidateQueries({ queryKey: ["accounts"] })
      queryClient.invalidateQueries({ queryKey: ["account"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
    },
  })
}
