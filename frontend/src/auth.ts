import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap, type User } from "./api/client";

export const meKey = ["auth", "me"] as const;
export const setupKey = ["setup"] as const;

export function useSetupStatus() {
  return useQuery({
    queryKey: setupKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/setup")),
  });
}

/** The logged-in user, or null when logged out. */
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async (): Promise<User | null> => {
      const result = await api.GET("/api/v1/auth/me");
      if (result.response.status === 401) return null;
      return unwrap(result);
    },
    staleTime: 60_000,
  });
}

export function useCurrentUser(): User {
  const { data } = useMe();
  if (!data) throw new Error("useCurrentUser used outside a logged-in route");
  return data;
}

type Credentials = { username: string; password: string };

export function useSetup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Credentials) => unwrap(await api.POST("/api/v1/setup", { body })),
    onSuccess: (user) => {
      queryClient.setQueryData(setupKey, { required: false });
      queryClient.setQueryData(meKey, user);
    },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Credentials) =>
      unwrap(await api.POST("/api/v1/auth/login", { body })),
    onSuccess: (user) => queryClient.setQueryData(meKey, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/auth/logout")),
    onSettled: () => {
      queryClient.setQueryData(meKey, null);
      // Drop everything cached for the previous user, but keep the auth gate's own queries.
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== meKey[0] && query.queryKey[0] !== setupKey[0],
      });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) =>
      unwrap(await api.POST("/api/v1/auth/password", { body })),
  });
}

export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
