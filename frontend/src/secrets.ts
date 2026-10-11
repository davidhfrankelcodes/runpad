import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";

export const secretsKey = ["secrets"] as const;

export function useSecrets() {
  return useQuery({
    queryKey: secretsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/secrets")),
  });
}

function useInvalidateSecrets() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: secretsKey });
}

export function useCreateSecret() {
  const onSuccess = useInvalidateSecrets();
  return useMutation({
    mutationFn: async (body: Schemas["SecretCreate"]) =>
      unwrap(await api.POST("/api/v1/secrets", { body })),
    onSuccess,
  });
}

export function useGenerateSshKey() {
  const onSuccess = useInvalidateSecrets();
  return useMutation({
    mutationFn: async (body: Schemas["SshKeyGenerate"]) =>
      unwrap(await api.POST("/api/v1/secrets/generate-ssh-key", { body })),
    onSuccess,
  });
}

export function useUpdateSecret() {
  const onSuccess = useInvalidateSecrets();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["SecretUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/secrets/{secret_id}", {
          params: { path: { secret_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useDeleteSecret() {
  const onSuccess = useInvalidateSecrets();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/secrets/{secret_id}", { params: { path: { secret_id: id } } }),
      ),
    onSuccess,
  });
}
