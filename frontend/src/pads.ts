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

type BoardRef = Schemas["BoardItem"];

/** One card on a pad's board: a button or a tile. Both share one order. */
export type BoardEntry =
  | { key: string; kind: "button"; position: number; button: PadButton }
  | { key: string; kind: "tile"; position: number; tile: PadTile };

/** The board's cards in order. Ties (from before boards shared one order) put tiles first. */
export function boardEntries(pad: PadDetail): BoardEntry[] {
  const entries: BoardEntry[] = [
    ...pad.tiles.map((tile) => ({ key: `tile:${tile.id}`, kind: "tile" as const, position: tile.position, tile })),
    ...pad.buttons.map((button) => ({
      key: `button:${button.id}`,
      kind: "button" as const,
      position: button.position,
      button,
    })),
  ];
  return entries.sort(
    (a, b) => a.position - b.position || (a.kind === b.kind ? 0 : a.kind === "tile" ? -1 : 1),
  );
}

function boardRef(key: string): BoardRef {
  const [kind, id = ""] = key.split(":");
  return { kind: kind === "tile" ? "tile" : "button", id };
}

/** Save a new board order. The board shows it at once; a refused order puts it back. */
export function useReorderBoard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ padId, keys }: { padId: string; keys: string[] }) =>
      unwrap(
        await api.PUT("/api/v1/pads/{pad_id}/order", {
          params: { path: { pad_id: padId } },
          body: { items: keys.map(boardRef) },
        }),
      ),
    onMutate: async ({ padId, keys }) => {
      const key = [...padsKey, padId];
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<PadDetail>(key);
      if (previous) {
        const position = new Map(keys.map((k, index) => [k, index]));
        queryClient.setQueryData<PadDetail>(key, {
          ...previous,
          buttons: previous.buttons.map((b) => ({ ...b, position: position.get(`button:${b.id}`) ?? b.position })),
          tiles: previous.tiles.map((t) => ({ ...t, position: position.get(`tile:${t.id}`) ?? t.position })),
        });
      }
      return { previous, key };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(context.key, context.previous);
    },
    onSettled: (_data, _error, { padId }) =>
      queryClient.invalidateQueries({ queryKey: [...padsKey, padId] }),
  });
}
