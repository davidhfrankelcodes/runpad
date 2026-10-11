import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";

export type Action = Schemas["ActionRead"];
export type ArgSpec = Action["args"][number];
export type ArgValue = string | number | boolean;
export type RunDetail = Schemas["RunDetail"];
export type RunSummary = Schemas["RunRead"];
export type ActionCreate =
  | Schemas["LocalActionCreate"]
  | Schemas["SshActionCreate"]
  | Schemas["HttpActionCreate"];
export type HttpSpec = Schemas["HttpSpec"];

export function isHttpSpec(spec: Action["spec"]): spec is HttpSpec {
  return !("script" in spec);
}

/** What pressing needs to know about an Action: admins have the full Action, members
 * the summary that comes with a pad's buttons. */
export type RunnableAction = Omit<Schemas["ButtonAction"], "kind">;

/** True when pressing should open the run dialog rather than start right away. */
export function needsDialog(action: RunnableAction): boolean {
  return action.args.length > 0 || action.confirm;
}

export const actionsKey = ["actions"] as const;
export const runsKey = ["runs"] as const;

export function useActions() {
  return useQuery({
    queryKey: actionsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/actions")),
  });
}

export function useAction(id: string | undefined) {
  return useQuery({
    queryKey: [...actionsKey, id],
    enabled: Boolean(id),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/actions/{action_id}", {
          params: { path: { action_id: id ?? "" } },
        }),
      ),
  });
}

function useInvalidateActions() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: actionsKey });
}

export function useSaveAction() {
  const onSuccess = useInvalidateActions();
  return useMutation({
    mutationFn: async ({ id, body }: { id?: string; body: ActionCreate }) => {
      if (!id) return unwrap(await api.POST("/api/v1/actions", { body }));
      const { executor, ...update } = body; // The executor cannot change.
      return unwrap(
        await api.PATCH("/api/v1/actions/{action_id}", {
          params: { path: { action_id: id } },
          body: update,
        }),
      );
    },
    onSuccess,
  });
}

export function useDeleteAction() {
  const onSuccess = useInvalidateActions();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/actions/{action_id}", { params: { path: { action_id: id } } }),
      ),
    onSuccess,
  });
}

export function useRunAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, args }: { id: string; args: Record<string, ArgValue> }) =>
      unwrap(
        await api.POST("/api/v1/actions/{action_id}/run", {
          params: { path: { action_id: id } },
          body: { args },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: runsKey }),
  });
}

export function useRuns() {
  return useQuery({
    queryKey: runsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/runs")),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: [...runsKey, id],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: id } } })),
  });
}

export function useCancelRun() {
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.POST("/api/v1/runs/{run_id}/cancel", { params: { path: { run_id: id } } }),
      ),
  });
}
