import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type ImportKind = components["schemas"]["ImportKind"]
export type ImportBatchOut = components["schemas"]["ImportBatchOut"]
export type UploadResult = components["schemas"]["UploadResult"]
export type PreviewOut = components["schemas"]["PreviewOut"]
export type CommitOut = components["schemas"]["CommitOut"]
export type CommitIn = components["schemas"]["CommitIn"]
export type PreviewIn = components["schemas"]["PreviewIn"]
export type JobStatusOut = components["schemas"]["JobStatusOut"]
export type SaveMappingIn = components["schemas"]["SaveMappingIn"]
export type ResolveInstrumentsIn = components["schemas"]["ResolveInstrumentsIn"]

function useInvalidateAfterImport() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["imports"] })
    queryClient.invalidateQueries({ queryKey: ["holdings"] })
    queryClient.invalidateQueries({ queryKey: ["transactions"] })
    queryClient.invalidateQueries({ queryKey: ["balances"] })
    queryClient.invalidateQueries({ queryKey: ["accounts"] })
    queryClient.invalidateQueries({ queryKey: ["account"] })
    queryClient.invalidateQueries({ queryKey: ["networth"] })
  }
}

export function useImportBatches() {
  return useQuery({
    queryKey: ["imports"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/imports", {})
      if (error) throw error
      return data
    },
  })
}

export function useUploadImport() {
  const invalidate = useInvalidateAfterImport()
  return useMutation({
    mutationFn: async ({
      kind,
      accountId,
      file,
    }: {
      kind: ImportKind
      accountId: number
      file: File
    }) => {
      const { data, error } = await apiClient.POST("/api/imports", {
        // openapi-fetch builds a multipart/form-data request body from this object because the
        // operation's requestBody content-type is multipart/form-data (see schema.d.ts).
        body: { kind, account_id: accountId, file: file as unknown as string },
        bodySerializer(body) {
          const fd = new FormData()
          fd.append("kind", body.kind)
          fd.append("account_id", String(body.account_id))
          fd.append("file", file)
          return fd
        },
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useSaveImportMapping() {
  return useMutation({
    mutationFn: async ({ batchId, payload }: { batchId: number; payload: SaveMappingIn }) => {
      const { data, error } = await apiClient.POST("/api/imports/{batch_id}/mapping", {
        params: { path: { batch_id: batchId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
  })
}

export function useResolveImportInstruments() {
  return useMutation({
    mutationFn: async ({ batchId, payload }: { batchId: number; payload: ResolveInstrumentsIn }) => {
      const { error } = await apiClient.POST("/api/imports/{batch_id}/instruments", {
        params: { path: { batch_id: batchId } },
        body: payload,
      })
      if (error) throw error
    },
  })
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: async ({ batchId, payload }: { batchId: number; payload: PreviewIn }) => {
      const { data, error } = await apiClient.POST("/api/imports/{batch_id}/preview", {
        params: { path: { batch_id: batchId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
  })
}

export function useCommitImport() {
  const invalidate = useInvalidateAfterImport()
  return useMutation({
    mutationFn: async ({ batchId, payload }: { batchId: number; payload: CommitIn }) => {
      const { data, error } = await apiClient.POST("/api/imports/{batch_id}/commit", {
        params: { path: { batch_id: batchId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useRollbackImport() {
  const invalidate = useInvalidateAfterImport()
  return useMutation({
    mutationFn: async (batchId: number) => {
      const { data, error } = await apiClient.POST("/api/imports/{batch_id}/rollback", {
        params: { path: { batch_id: batchId } },
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useImportJobStatus(jobId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["imports", "job", jobId],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/imports/jobs/{job_id}", {
        params: { path: { job_id: jobId! } },
      })
      if (error) throw error
      return data
    },
    enabled: enabled && jobId !== undefined,
    refetchInterval: (query) => (query.state.data?.status === "running" || query.state.data?.status === "pending" ? 500 : false),
  })
}
