import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type AccountSummary = components["schemas"]["AccountSummary"]
export type AccountDetail = components["schemas"]["AccountDetail"]
export type AccountCreate = components["schemas"]["AccountCreate"]
export type AccountUpdate = components["schemas"]["AccountUpdate"]
export type Category = components["schemas"]["Category"]
export type GrowthModelIn = components["schemas"]["GrowthModelIn"]

interface AccountFilters {
  personId?: number
  category?: Category
  includeArchived?: boolean
}

export function useAccounts(filters: AccountFilters = {}) {
  return useQuery({
    queryKey: ["accounts", filters],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts", {
        params: {
          query: {
            person_id: filters.personId,
            category: filters.category,
            include_archived: filters.includeArchived ?? false,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

export function useAccount(id: number | undefined) {
  return useQuery({
    queryKey: ["account", id],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}", {
        params: { path: { account_id: id! } },
      })
      if (error) throw error
      return data
    },
    enabled: id !== undefined,
  })
}

async function fetchAccountHistory(id: number, dateFrom?: string, dateTo?: string) {
  const { data, error } = await apiClient.GET("/api/accounts/{account_id}/history", {
    params: { path: { account_id: id }, query: { date_from: dateFrom, date_to: dateTo } },
  })
  if (error) throw error
  return data
}

export function useAccountHistory(id: number | undefined, dateFrom?: string, dateTo?: string) {
  return useQuery({
    queryKey: ["account", id, "history", dateFrom ?? null, dateTo ?? null],
    queryFn: () => fetchAccountHistory(id!, dateFrom, dateTo),
    enabled: id !== undefined,
  })
}

/**
 * History for several accounts at once. There is no per-category history endpoint, so the
 * category pages (Pensions, Investments) sum a handful of per-account histories client-side to
 * draw the solid half of their current-vs-projected chart. Query keys match `useAccountHistory`.
 */
/** `dateFrom` omitted uses the server default (the last year). */
export function useAccountHistories(ids: number[], dateFrom?: string) {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: ["account", id, "history", dateFrom ?? null, null],
      queryFn: () => fetchAccountHistory(id, dateFrom),
    })),
  })
}

function useInvalidateAccounts() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account"] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
    queryClient.invalidateQueries({ queryKey: ["quick-update"] })
  }
}

export function useCreateAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async (payload: AccountCreate) => {
      const { data, error } = await apiClient.POST("/api/accounts", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: AccountUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/accounts/{account_id}", {
        params: { path: { account_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function usePutGrowthModel() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: GrowthModelIn }) => {
      const { data, error } = await apiClient.PUT("/api/accounts/{account_id}/growth-model", {
        params: { path: { account_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteAccount() {
  const invalidate = useInvalidateAccounts()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/accounts/{account_id}", {
        params: { path: { account_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}
