import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";

export type ApiToken = Schemas["ApiTokenRead"];
export type ApiTokenCreate = Schemas["ApiTokenCreate"];

const tokensKey = ["api-tokens"] as const;

export function useApiTokens() {
  return useQuery({
    queryKey: tokensKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/auth/tokens")),
  });
}

export function useCreateApiToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ApiTokenCreate) =>
      unwrap(await api.POST("/api/v1/auth/tokens", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tokensKey }),
  });
}

export function useRevokeApiToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/auth/tokens/{token_id}", { params: { path: { token_id: id } } }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tokensKey }),
  });
}
