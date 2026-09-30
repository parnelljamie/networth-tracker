import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/api/client"

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/health")
      if (error) throw error
      return data
    },
    refetchInterval: 60_000,
    retry: 1,
  })
}
