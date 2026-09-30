import { useEffect, useRef } from "react"
import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/api/client"
import type { components } from "@/api/schema"

export type Trading212LinkOut = components["schemas"]["Trading212LinkOut"]
export type Trading212ConnectIn = components["schemas"]["Trading212ConnectIn"]
export type Trading212NewAccountIn = components["schemas"]["Trading212NewAccountIn"]
export type Trading212ChangesOut = components["schemas"]["Trading212ChangesOut"]

/** Everything a sync can change, except the link itself. */
function invalidateSyncedData(queryClient: QueryClient) {
  for (const key of ["recurring", "imports", "holdings", "transactions", "accounts", "account", "networth"]) {
    queryClient.invalidateQueries({ queryKey: [key] })
  }
}

function useInvalidateAfterSync() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: ["trading212"] })
    invalidateSyncedData(queryClient)
  }
}

/** The account's Trading 212 link, or null when it isn't linked. Polls every few seconds while a
 * sync is running (a first sync can take minutes: the history endpoints allow 6 requests a
 * minute), and refreshes holdings etc. once, when it finishes. */
export function useTrading212Link(accountId: number | undefined) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ["trading212", accountId ?? null],
    enabled: accountId !== undefined,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/trading212/links/{account_id}", {
        params: { path: { account_id: accountId! } },
      })
      if (error) throw error
      return data ?? null
    },
    refetchInterval: (q) => (q.state.data?.status === "running" ? 3000 : false),
    // Keep checking while the window is in the background: a first sync takes minutes, and the
    // holdings should be current when the user comes back.
    refetchIntervalInBackground: true,
  })

  // React to the finished result once it's stored. (Invalidating from inside queryFn restarts
  // this same query before its result lands, which loops forever.)
  const status = query.data?.status
  const previousStatus = useRef(status)
  useEffect(() => {
    if (previousStatus.current === "running" && status !== undefined && status !== "running") {
      invalidateSyncedData(queryClient)
    }
    previousStatus.current = status
  }, [status, queryClient])

  return query
}

/** Every linked account (Settings → Trading 212, and the app-wide changes popup). Polls every
 * few seconds while any of them is syncing, and once a minute otherwise so syncs the backend
 * starts by itself (daily, at startup) surface too. Refreshes holdings etc. when a sync ends. */
export function useTrading212Links(enabled = true) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ["trading212", "list"],
    enabled,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/trading212/links")
      if (error) throw error
      return data
    },
    refetchInterval: (q) => (q.state.data?.some((l) => l.status === "running") ? 3000 : 60_000),
    refetchIntervalInBackground: true,
  })

  const running = query.data?.some((l) => l.status === "running") ?? false
  const wasRunning = useRef(running)
  useEffect(() => {
    if (wasRunning.current && !running) invalidateSyncedData(queryClient)
    wasRunning.current = running
  }, [running, queryClient])

  return query
}

/** Syncs waiting to be accepted, for the popup. `batchIds` is part of the key, so a new sync
 * (a new pending batch) fetches fresh figures. */
export function useTrading212Changes(batchIds: number[]) {
  return useQuery({
    queryKey: ["trading212", "changes", batchIds],
    enabled: batchIds.length > 0,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/trading212/changes")
      if (error) throw error
      return data
    },
  })
}

export function useAcceptTrading212Changes() {
  const invalidate = useInvalidateAfterSync()
  return useMutation({
    mutationFn: async (accountId: number) => {
      const { data, error } = await apiClient.POST("/api/trading212/links/{account_id}/accept", {
        params: { path: { account_id: accountId } },
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

/** Update prices: sync every linked Trading 212 account in the background. */
export function useSyncAllTrading212() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/api/trading212/sync")
      if (error) throw error
      return data
    },
    onSuccess: (data) => queryClient.setQueryData(["trading212", "list"], data),
  })
}

/** Settings: create a Stocks ISA or Invest account and link it in one go. */
export function useConnectTrading212NewAccount() {
  const invalidate = useInvalidateAfterSync()
  return useMutation({
    mutationFn: async (payload: Trading212NewAccountIn) => {
      const { data, error } = await apiClient.POST("/api/trading212/links", { body: payload })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useConnectTrading212() {
  const invalidate = useInvalidateAfterSync()
  return useMutation({
    mutationFn: async ({ accountId, payload }: { accountId: number; payload: Trading212ConnectIn }) => {
      const { data, error } = await apiClient.PUT("/api/trading212/links/{account_id}", {
        params: { path: { account_id: accountId } },
        body: payload,
      })
      if (error) throw error
      return data
    },
    onSuccess: invalidate,
  })
}

export function useSetTrading212AutoSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ accountId, autoSync }: { accountId: number; autoSync: boolean }) => {
      const { data, error } = await apiClient.PATCH("/api/trading212/links/{account_id}", {
        params: { path: { account_id: accountId } },
        body: { auto_sync: autoSync },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trading212"] }),
  })
}

export function useDisconnectTrading212() {
  const invalidate = useInvalidateAfterSync()
  return useMutation({
    mutationFn: async (accountId: number) => {
      const { error } = await apiClient.DELETE("/api/trading212/links/{account_id}", {
        params: { path: { account_id: accountId } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })
}

export function useSyncTrading212() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (accountId: number) => {
      const { data, error } = await apiClient.POST("/api/trading212/links/{account_id}/sync", {
        params: { path: { account_id: accountId } },
      })
      if (error) throw error
      return data
    },
    onSuccess: (data, accountId) => {
      queryClient.setQueryData(["trading212", accountId], data)
      // The Settings list too, so it sees "running", polls, and shows the outcome.
      queryClient.setQueryData<Trading212LinkOut[]>(["trading212", "list"], (links) =>
        data ? links?.map((l) => (l.account_id === accountId ? data : l)) : links
      )
    },
  })
}
