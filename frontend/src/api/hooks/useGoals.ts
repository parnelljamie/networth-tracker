import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type GoalOut = components["schemas"]["GoalOut"]
export type GoalCreate = components["schemas"]["GoalCreate"]
export type GoalUpdate = components["schemas"]["GoalUpdate"]
export type GoalScope = components["schemas"]["GoalScope"]

function useInvalidateGoals() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ["goals"] })
}

export function useGoals() {
  return useQuery({
    queryKey: ["goals"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/goals", {})
      if (error) throw error
      return data
    },
  })
}

export function useCreateGoal() {
  const invalidate = useInvalidateGoals()
  return useMutation({
    mutationFn: async (payload: GoalCreate) => {
      const { data, error } = await apiClient.POST("/api/goals", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateGoal() {
  const invalidate = useInvalidateGoals()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: GoalUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/goals/{goal_id}", {
        params: { path: { goal_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteGoal() {
  const invalidate = useInvalidateGoals()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/goals/{goal_id}", {
        params: { path: { goal_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}
