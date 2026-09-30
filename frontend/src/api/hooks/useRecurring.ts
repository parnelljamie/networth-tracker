import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type RecurringPlanOut = components["schemas"]["RecurringPlanOut"]
export type RecurringPlanCreate = components["schemas"]["RecurringPlanCreate"]
export type RecurringPlanUpdate = components["schemas"]["RecurringPlanUpdate"]
export type UpcomingItem = components["schemas"]["UpcomingItem"]
export type AllowanceUsageOut = components["schemas"]["AllowanceUsageOut"]

function useInvalidateRecurring() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["recurring"] })
    queryClient.invalidateQueries({ queryKey: ["allowances"] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account"] })
  }
}

export function useRecurringPlans(params: { accountId?: number; personId?: number } = {}) {
  return useQuery({
    queryKey: ["recurring", "list", params.accountId ?? null, params.personId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/recurring", {
        params: { query: { account_id: params.accountId, person_id: params.personId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useUpcomingPlans(params: { days?: number; personId?: number } = {}) {
  return useQuery({
    queryKey: ["recurring", "upcoming", params.days ?? 60, params.personId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/recurring/upcoming", {
        params: { query: { days: params.days ?? 60, person_id: params.personId } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCreateRecurringPlan() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async (payload: RecurringPlanCreate) => {
      const { data, error } = await apiClient.POST("/api/recurring", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateRecurringPlan() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: RecurringPlanUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/recurring/{plan_id}", {
        params: { path: { plan_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteRecurringPlan() {
  const invalidate = useInvalidateRecurring()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/recurring/{plan_id}", {
        params: { path: { plan_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}

export function useAllowances(params: { taxYear?: number; personId?: number } = {}) {
  return useQuery({
    queryKey: ["allowances", params.taxYear ?? null, params.personId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/allowances", {
        params: { query: { tax_year: params.taxYear, person_id: params.personId } },
      })
      if (error) throw error
      return data
    },
  })
}
