import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type LoanDetailsOut = components["schemas"]["LoanDetailsOut"]
export type LoanDetailsIn = components["schemas"]["LoanDetailsIn"]
export type RatePeriodOut = components["schemas"]["RatePeriodOut"]
export type RatePeriodIn = components["schemas"]["RatePeriodIn"]
export type OverpaymentOut = components["schemas"]["OverpaymentOut"]
export type OverpaymentIn = components["schemas"]["OverpaymentIn"]
export type LoanSchedule = components["schemas"]["LoanSchedule"]
export type ScheduleRowOut = components["schemas"]["ScheduleRowOut"]
export type SimulateIn = components["schemas"]["SimulateIn"]
export type LoanSimulation = components["schemas"]["LoanSimulation"]
export type EquityOut = components["schemas"]["EquityOut"]

function useInvalidateLoans() {
  const queryClient = useQueryClient()
  return (accountId: number) => {
    queryClient.invalidateQueries({ queryKey: ["loan", accountId] })
    queryClient.invalidateQueries({ queryKey: ["rate-periods", accountId] })
    queryClient.invalidateQueries({ queryKey: ["overpayments", accountId] })
    queryClient.invalidateQueries({ queryKey: ["schedule", accountId] })
    queryClient.invalidateQueries({ queryKey: ["equity"] })
    queryClient.invalidateQueries({ queryKey: ["account", accountId] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
  }
}

export function usePutLoan() {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: LoanDetailsIn }) => {
      const { data, error } = await apiClient.PUT("/api/accounts/{account_id}/loan", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => invalidate(vars.accountId),
  })
}

export function useRatePeriods(accountId: number | undefined) {
  return useQuery({
    queryKey: ["rate-periods", accountId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/rate-periods", {
        params: { path: { account_id: accountId! } },
      })
      if (error) throw error
      return data
    },
    enabled: accountId !== undefined,
  })
}

export function useCreateRatePeriod() {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: RatePeriodIn }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/rate-periods", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => invalidate(vars.accountId),
  })
}

export function useUpdateRatePeriod(accountId: number) {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: RatePeriodIn }) => {
      const { data, error } = await apiClient.PATCH("/api/rate-periods/{rate_period_id}", {
        params: { path: { rate_period_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => invalidate(accountId),
  })
}

export function useDeleteRatePeriod(accountId: number) {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/rate-periods/{rate_period_id}", {
        params: { path: { rate_period_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(accountId),
  })
}

export function useOverpayments(accountId: number | undefined) {
  return useQuery({
    queryKey: ["overpayments", accountId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/overpayments", {
        params: { path: { account_id: accountId! } },
      })
      if (error) throw error
      return data
    },
    enabled: accountId !== undefined,
  })
}

export function useCreateOverpayment() {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: OverpaymentIn }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/overpayments", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => invalidate(vars.accountId),
  })
}

export function useDeleteOverpayment(accountId: number) {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/overpayments/{overpayment_id}", {
        params: { path: { overpayment_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => invalidate(accountId),
  })
}

export function useSchedule(accountId: number | undefined, includePlanned = true) {
  return useQuery({
    queryKey: ["schedule", accountId, includePlanned],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/schedule", {
        params: { path: { account_id: accountId! }, query: { include_planned: includePlanned } },
      })
      if (error) throw error
      return data
    },
    enabled: accountId !== undefined,
  })
}

export function useSimulateSchedule() {
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: SimulateIn }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/schedule/simulate", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
  })
}

export function useSaveSimulationAsPlan() {
  const invalidate = useInvalidateLoans()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: SimulateIn }) => {
      const { data, error } = await apiClient.POST("/api/accounts/{account_id}/schedule/simulate/save", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => invalidate(vars.accountId),
  })
}

export function useEquity(propertyAccountId: number | undefined) {
  return useQuery({
    queryKey: ["equity", propertyAccountId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/accounts/{account_id}/equity", {
        params: { path: { account_id: propertyAccountId! } },
      })
      if (error) throw error
      return data
    },
    enabled: propertyAccountId !== undefined,
  })
}
