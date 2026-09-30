import { useMutation, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type DbPensionDetailsIn = components["schemas"]["DbPensionDetailsIn"]
export type DbPensionSummaryOut = components["schemas"]["DbPensionSummaryOut"]

export function usePutDbPension() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: DbPensionDetailsIn }) => {
      const { data, error } = await apiClient.PUT("/api/accounts/{account_id}/db-pension", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["account", vars.accountId] })
      queryClient.invalidateQueries({ queryKey: ["accounts"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
      queryClient.invalidateQueries({ queryKey: ["projection"] })
      queryClient.invalidateQueries({ queryKey: ["projection-compare"] })
    },
  })
}
