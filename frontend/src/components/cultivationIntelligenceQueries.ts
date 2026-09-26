import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import { intelligenceBase, intelligenceScope } from "./cultivationIntelligenceTypes";

export function useIntelligence<T>(path: string, enabled = true) {
  return useQuery({
    queryKey: ["cultivation-intelligence", ...intelligenceScope(), path],
    queryFn: ({ signal }) => apiGet<T>(`${intelligenceBase}${path}`, signal),
    retry: false,
    enabled,
  });
}

export function useIntelligenceWrite<T = unknown>(path: string, onSaved?: (data: T) => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) => apiPost<T>(`${intelligenceBase}${path}`, body),
    retry: false,
    onSuccess: data => {
      void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] });
      onSaved?.(data);
    },
  });
}
