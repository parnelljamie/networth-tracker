import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/settings", {})
      if (error) throw error
      return data as Record<string, unknown>
    },
  })
}

export function usePatchSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (patch: Record<string, unknown>) => {
      const { data, error } = await apiClient.PATCH("/api/settings", { body: patch })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] })
      // Growth, inflation and return-rate settings feed every projection.
      queryClient.invalidateQueries({ queryKey: ["projection"] })
      queryClient.invalidateQueries({ queryKey: ["projection-compare"] })
    },
  })
}

export function useBackups() {
  return useQuery({
    queryKey: ["backups"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/backups", {})
      if (error) throw error
      return data
    },
  })
}

export function useRunBackup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/backup", {})
      if (error) throw error
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["backups"] })
    },
  })
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system-info"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/system/info", {})
      if (error) throw error
      return data
    },
  })
}

export function useOpenDataFolder() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/system/open-data-folder", {})
      if (error) throw error
      return data
    },
  })
}

/** Opens the Windows folder picker on this PC; resolves to the chosen path, or null if cancelled. */
export function useChooseFolder() {
  return useMutation({
    mutationFn: async (params: { start?: string | null; title?: string }) => {
      const { data, error } = await apiClient.POST("/api/system/choose-folder", {
        body: { start: params.start ?? null, title: params.title ?? "Choose a folder" },
      })
      if (error) throw error
      return data.path ?? null
    },
  })
}

/** Settings -> Updates. A POST because it goes to GitHub, and only when the user asks. */
export function useCheckForUpdate() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/system/update/check", {})
      if (error) throw error
      return data
    },
  })
}

/** Windows: downloads and runs the installer, which closes and reopens the app. */
export function useInstallUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/system/update/install", {})
      if (error) throw error
      return data
    },
    onSuccess: (status) => queryClient.setQueryData(["update-status"], status),
  })
}

/** Polls the download while one is running. */
export function useUpdateStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["update-status"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/system/update/status", {})
      if (error) throw error
      return data
    },
    enabled,
    refetchInterval: (query) => {
      const state = query.state.data?.state
      return state === "downloading" || state === "installing" ? 1000 : false
    },
  })
}
