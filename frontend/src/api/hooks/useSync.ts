import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import { useHealth } from "@/api/hooks/useHealth"
import type { components } from "@/api/schema"

export type SyncReport = components["schemas"]["SyncReportOut"]
export type SyncClient = components["schemas"]["SyncClientOut"]

/** "desktop" on the PC, "phone" in the Android app (docs/07-mobile.md "Roles"). */
export function useRole(): "desktop" | "phone" {
  const { data } = useHealth()
  return data?.role === "phone" ? "phone" : "desktop"
}

// --- PC: pairing -----------------------------------------------------------------------------

export function useSyncStatus(enabled = true) {
  return useQuery({
    queryKey: ["sync", "status"],
    enabled,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/sync/status")
      if (error) throw error
      return data
    },
  })
}

export function useSetSyncEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (enabled: boolean) => {
      const { data, error } = await apiClient.PUT("/api/sync/enabled", { body: { enabled } })
      if (error) throw error
      return data
    },
    onSuccess: (data) => queryClient.setQueryData(["sync", "status"], data),
  })
}

export function usePairPhone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      const { data, error } = await apiClient.POST("/api/sync/pair", { body: { name } })
      if (error) throw error
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sync", "status"] }),
  })
}

export function useUnpairPhone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (deviceId: number) => {
      const { error } = await apiClient.DELETE("/api/sync/devices/{device_id}", {
        params: { path: { device_id: deviceId } },
      })
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sync", "status"] }),
  })
}

// --- Phone: syncing with the PC ----------------------------------------------------------------

export function useSyncClient(enabled = true) {
  return useQuery({
    queryKey: ["sync", "client"],
    enabled,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/sync/client")
      if (error) throw error
      return data
    },
    refetchInterval: 30_000,
  })
}

export function usePairWithPc() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (pairingUri: string) => {
      const { data, error } = await apiClient.POST("/api/sync/client/pair", {
        body: { pairing_uri: pairingUri },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data) => queryClient.setQueryData(["sync", "client"], data),
  })
}

export function useForgetPc() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await apiClient.DELETE("/api/sync/client")
      if (error) throw error
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sync", "client"] }),
  })
}

export function useSyncNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/sync/client/sync")
      if (error) throw error
      return data
    },
    onSuccess: (report) => {
      // A successful sync replaced the whole database: every cached figure is out of date.
      if (report.status === "ok") queryClient.invalidateQueries()
      else queryClient.invalidateQueries({ queryKey: ["sync", "client"] })
    },
  })
}
