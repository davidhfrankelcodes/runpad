import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "./api/client";

export type Pad = Schemas["PadRead"];
export type PadDetail = Schemas["PadDetail"];
export type PadButton = Schemas["ButtonRead"];
export type ButtonColor = PadButton["color"];

export const BUTTON_COLORS: ButtonColor[] = ["slate", "emerald", "sky", "amber", "red", "violet"];

export const padsKey = ["pads"] as const;

export function usePads() {
  return useQuery({
    queryKey: padsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/pads")),
  });
}

export function usePad(id: string) {
  return useQuery({
    queryKey: [...padsKey, id],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/pads/{pad_id}", { params: { path: { pad_id: id } } })),
  });
}

function useInvalidatePads() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: padsKey });
}

export function useCreatePad() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async (body: Schemas["PadCreate"]) =>
      unwrap(await api.POST("/api/v1/pads", { body })),
    onSuccess,
  });
}

export function useUpdatePad() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["PadUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/pads/{pad_id}", { params: { path: { pad_id: id } }, body }),
      ),
    onSuccess,
  });
}

export function useDeletePad() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/pads/{pad_id}", { params: { path: { pad_id: id } } })),
    onSuccess,
  });
}

export function useCreateButton() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ padId, ...body }: Schemas["ButtonCreate"] & { padId: string }) =>
      unwrap(
        await api.POST("/api/v1/pads/{pad_id}/buttons", {
          params: { path: { pad_id: padId } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useUpdateButton() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["ButtonUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/buttons/{button_id}", {
          params: { path: { button_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useDeleteButton() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/buttons/{button_id}", { params: { path: { button_id: id } } }),
      ),
    onSuccess,
  });
}

export function useReorderPads() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async (ids: string[]) =>
      unwrap(await api.PUT("/api/v1/pads/order", { body: { ids } })),
    onSuccess,
  });
}

export function useReorderButtons() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ padId, ids }: { padId: string; ids: string[] }) =>
      unwrap(
        await api.PUT("/api/v1/pads/{pad_id}/buttons/order", {
          params: { path: { pad_id: padId } },
          body: { ids },
        }),
      ),
    onSuccess,
  });
}

export type PadTile = Schemas["TileRead"];
export type TileState = NonNullable<PadTile["state"]>;

export function useCreateTile() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ padId, ...body }: Schemas["TileCreate"] & { padId: string }) =>
      unwrap(
        await api.POST("/api/v1/pads/{pad_id}/tiles", { params: { path: { pad_id: padId } }, body }),
      ),
    onSuccess,
  });
}

export function useUpdateTile() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["TileUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/tiles/{tile_id}", { params: { path: { tile_id: id } }, body }),
      ),
    onSuccess,
  });
}

export function useDeleteTile() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/tiles/{tile_id}", { params: { path: { tile_id: id } } })),
    onSuccess,
  });
}

export function useReorderTiles() {
  const onSuccess = useInvalidatePads();
  return useMutation({
    mutationFn: async ({ padId, ids }: { padId: string; ids: string[] }) =>
      unwrap(
        await api.PUT("/api/v1/pads/{pad_id}/tiles/order", {
          params: { path: { pad_id: padId } },
          body: { ids },
        }),
      ),
    onSuccess,
  });
}
