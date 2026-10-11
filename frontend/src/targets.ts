import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";

export type Target = Schemas["TargetRead"];
export type SshConfig = Schemas["SshConfigRead"];
export type HttpConfig = Schemas["HttpConfig"];
export type HostKey = Schemas["HostKeyRead"];

export function isSshConfig(config: Target["config"]): config is SshConfig {
  return "host_key" in config;
}

const targetsKey = ["targets"] as const;

export function useTargets() {
  return useQuery({
    queryKey: targetsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/targets")),
  });
}

function useInvalidateTargets() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: targetsKey });
}

export function useCreateTarget() {
  const onSuccess = useInvalidateTargets();
  return useMutation({
    mutationFn: async (body: Schemas["SshTargetCreate"] | Schemas["HttpTargetCreate"]) =>
      unwrap(await api.POST("/api/v1/targets", { body })),
    onSuccess,
  });
}

export function useUpdateTarget() {
  const onSuccess = useInvalidateTargets();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["TargetUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/targets/{target_id}", {
          params: { path: { target_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useDeleteTarget() {
  const onSuccess = useInvalidateTargets();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/targets/{target_id}", { params: { path: { target_id: id } } }),
      ),
    onSuccess,
  });
}

export function useTestTarget() {
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST("/api/v1/targets/{target_id}/test", {
          params: { path: { target_id: id } },
        }),
      ),
  });
}

export function useScanHostKey() {
  return useMutation({
    mutationFn: async (body: Schemas["HostKeyScanRequest"]) =>
      unwrap(await api.POST("/api/v1/targets/scan-host-key", { body })),
  });
}
