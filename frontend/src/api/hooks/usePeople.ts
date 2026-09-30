import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type Person = components["schemas"]["PersonOut"]
export type PersonCreate = components["schemas"]["PersonCreate"]
export type PersonUpdate = components["schemas"]["PersonUpdate"]

export function usePeople(includeArchived = false) {
  return useQuery({
    queryKey: ["people", { includeArchived }],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/people", {
        params: { query: { include_archived: includeArchived } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCreatePerson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: PersonCreate) => {
      const { data, error } = await apiClient.POST("/api/people", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["people"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
    },
  })
}

export function useUpdatePerson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: PersonUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/people/{person_id}", {
        params: { path: { person_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["people"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
    },
  })
}

export function useDeletePerson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/people/{person_id}", {
        params: { path: { person_id: id } },
      })
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["people"] })
      queryClient.invalidateQueries({ queryKey: ["networth"] })
    },
  })
}
