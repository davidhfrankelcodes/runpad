import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";
import { meKey } from "./auth";

const usersKey = ["users"] as const;

export function useUsers() {
  return useQuery({
    queryKey: usersKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/users")),
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["UserCreate"]) =>
      unwrap(await api.POST("/api/v1/users", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["UserUpdate"] & { id: string }) =>
      unwrap(await api.PATCH("/api/v1/users/{user_id}", { params: { path: { user_id: id } }, body })),
    onSuccess: () => {
      // The admin may have changed their own role.
      void queryClient.invalidateQueries({ queryKey: usersKey });
      void queryClient.invalidateQueries({ queryKey: meKey });
    },
  });
}
