import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { runsKey } from "./actions";
import type { Schemas } from "./api/client";
import { padsKey, type Pad, type PadDetail } from "./pads";

type StateRead = Schemas["StateRead"];

/** Follows /api/v1/events while mounted: State changes update the tiles of cached pads,
 * Run changes refresh run lists. On every (re)connection the server sends `ready` once
 * subscribed, and everything is refetched, since changes before that were not sent. */
export function useLiveEvents() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const source = new EventSource("/api/v1/events");

    source.addEventListener("ready", () => {
      void queryClient.invalidateQueries({ queryKey: padsKey });
      void queryClient.invalidateQueries({ queryKey: runsKey });
    });
    source.addEventListener("state", (event) => {
      const state = JSON.parse((event as MessageEvent<string>).data) as StateRead;
      // Matches the pad list too; only pad details have tiles.
      queryClient.setQueriesData<PadDetail | Pad[]>({ queryKey: padsKey }, (pad) =>
        pad && !Array.isArray(pad)
          ? {
              ...pad,
              tiles: pad.tiles.map((tile) =>
                tile.feature_instance_id === state.feature_instance_id && tile.state_key === state.key
                  ? { ...tile, state }
                  : tile,
              ),
            }
          : pad,
      );
    });
    source.addEventListener("run", () => {
      void queryClient.invalidateQueries({ queryKey: runsKey });
    });
    return () => source.close();
  }, [queryClient]);
}
