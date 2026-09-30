import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type ProjectionOut = components["schemas"]["ProjectionOut"]
export type ScenarioOut = components["schemas"]["ScenarioOut"]
export type ScenarioIn = components["schemas"]["ScenarioIn"]
export type ScenarioUpdate = components["schemas"]["ScenarioUpdate"]
export type ScenarioEventOut = components["schemas"]["ScenarioEventOut"]
export type ScenarioEventIn = components["schemas"]["ScenarioEventIn"]
export type CompareOut = components["schemas"]["CompareOut"]
export type MilestoneOut = components["schemas"]["MilestoneOut"]
export type MonteCarloOut = components["schemas"]["MonteCarloOut"]

export function useProjection(params: {
  personId?: number
  scenarioId?: number
  months?: number
  realTerms?: boolean
  byAccount?: boolean
}) {
  return useQuery({
    queryKey: [
      "projection",
      params.personId ?? null,
      params.scenarioId ?? null,
      params.months ?? 360,
      params.realTerms ?? false,
      params.byAccount ?? false,
    ],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/projection", {
        params: {
          query: {
            person_id: params.personId,
            scenario_id: params.scenarioId,
            months: params.months ?? 360,
            real_terms: params.realTerms ?? false,
            by_account: params.byAccount ?? false,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

/** Range of outcomes (p10–p90 of the total) from the Monte Carlo endpoint. Keyed under
 *  "projection" so everything that invalidates projections refreshes it too. */
export function useMonteCarlo(params: {
  personId?: number
  scenarioId?: number
  months: number
  realTerms: boolean
  enabled?: boolean
}) {
  return useQuery({
    queryKey: ["projection", "monte-carlo", params.personId ?? null, params.scenarioId ?? null, params.months, params.realTerms],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/projection/monte-carlo", {
        params: {
          query: {
            person_id: params.personId,
            scenario_id: params.scenarioId,
            months: params.months,
            real_terms: params.realTerms,
          },
        },
      })
      if (error) throw error
      return data
    },
    enabled: params.enabled ?? true,
  })
}

async function fetchProjection(params: {
  personId?: number
  scenarioId?: number
  months: number
  realTerms: boolean
  byAccount: boolean
}) {
  const { data, error } = await apiClient.GET("/api/projection", {
    params: {
      query: {
        person_id: params.personId,
        scenario_id: params.scenarioId,
        months: params.months,
        real_terms: params.realTerms,
        by_account: params.byAccount,
      },
    },
  })
  if (error) throw error
  return data
}

/**
 * One `by_account` projection per person, each run to that person's own horizon — people retire
 * in different years, so a household pension pot "at retirement" is the sum of each person's pot
 * at *their* date, not everyone's at one shared date.
 *
 * The query keys match `useProjection`'s exactly, so a child component calling `useProjection`
 * with the same person/months reads this cache instead of refetching.
 */
export function useProjectionsForPeople(requests: { personId: number; months: number }[]) {
  return useQueries({
    queries: requests.map((request) => ({
      queryKey: ["projection", request.personId, null, request.months, false, true],
      queryFn: () =>
        fetchProjection({
          personId: request.personId,
          months: request.months,
          realTerms: false,
          byAccount: true,
        }),
    })),
  })
}

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scenarios")
      if (error) throw error
      return data
    },
  })
}

function useInvalidateProjection() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["projection"] })
    queryClient.invalidateQueries({ queryKey: ["projection-compare"] })
    queryClient.invalidateQueries({ queryKey: ["scenarios"] })
    queryClient.invalidateQueries({ queryKey: ["scenario-events"] })
  }
}

export function useCreateScenario() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async (payload: ScenarioIn) => {
      const { data, error } = await apiClient.POST("/api/scenarios", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateScenario() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: ScenarioUpdate }) => {
      const { data, error } = await apiClient.PATCH("/api/scenarios/{scenario_id}", {
        params: { path: { scenario_id: id } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteScenario() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await apiClient.DELETE("/api/scenarios/{scenario_id}", {
        params: { path: { scenario_id: id } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}

export function useProjectionCompare(params: {
  scenarioIds: number[]
  personId?: number
  months?: number
  realTerms?: boolean
}) {
  return useQuery({
    queryKey: [
      "projection-compare",
      [...params.scenarioIds].sort(),
      params.personId ?? null,
      params.months ?? 360,
      params.realTerms ?? false,
    ],
    queryFn: async () => {
      const { data, error } = await apiClient.POST("/api/projection/compare", {
        body: {
          scenario_ids: params.scenarioIds,
          person_id: params.personId,
          months: params.months ?? 360,
          real_terms: params.realTerms ?? false,
        },
      })
      if (error) throw error
      return data
    },
    enabled: params.scenarioIds.length > 0,
  })
}

export function useCompareProjection() {
  return useMutation({
    mutationFn: async (payload: {
      scenario_ids: number[]
      person_id?: number
      months?: number
      real_terms?: boolean
    }) => {
      const { data, error } = await apiClient.POST("/api/projection/compare", { body: payload })
      if (error) throw error
      return data
    },
  })
}

export function useScenarioEvents(scenarioId?: number) {
  return useQuery({
    queryKey: ["scenario-events", scenarioId ?? null],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/scenarios/{scenario_id}/events", {
        params: { path: { scenario_id: scenarioId! } },
      })
      if (error) throw error
      return data
    },
    enabled: scenarioId !== undefined,
  })
}

export function useCreateScenarioEvent() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async ({ scenarioId, payload }: { scenarioId: number; payload: ScenarioEventIn }) => {
      const { data, error } = await apiClient.POST("/api/scenarios/{scenario_id}/events", {
        params: { path: { scenario_id: scenarioId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateScenarioEvent() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async ({ eventId, payload }: { eventId: number; payload: ScenarioEventIn }) => {
      const { data, error } = await apiClient.PATCH("/api/scenario-events/{event_id}", {
        params: { path: { event_id: eventId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteScenarioEvent() {
  const invalidate = useInvalidateProjection()
  return useMutation({
    mutationFn: async (eventId: number) => {
      const { error } = await apiClient.DELETE("/api/scenario-events/{event_id}", {
        params: { path: { event_id: eventId } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}
