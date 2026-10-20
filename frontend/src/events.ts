import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { runsKey } from "./actions";
import { instancesKey, type FeatureInstance } from "./features";
import { withCheck } from "./history";
import type { Schemas } from "./api/client";
import { padsKey, type Pad, type PadDetail } from "./pads";

type StateRead = Schemas["StateRead"];
type RunRead = Schemas["RunRead"];

/** Follows /api/v1/events while mounted: State changes update the tiles of cached pads and
 * the Tiles page (their State, and the current bar of their history), Run changes refresh
 * run lists and the last-run line of buttons for that action. On every (re)connection the
 * server sends `ready` once subscribed, and everything is refetched, since changes before
 * that were not sent. */
export function useLiveEvents() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const source = new EventSource("/api/v1/events");

    source.addEventListener("ready", () => {
      void queryClient.invalidateQueries({ queryKey: padsKey });
      void queryClient.invalidateQueries({ queryKey: runsKey });
      void queryClient.invalidateQueries({ queryKey: instancesKey });
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
                  ? { ...tile, state, history: withCheck(tile.history, state.tone) }
                  : tile,
              ),
            }
          : pad,
      );
      queryClient.setQueryData<FeatureInstance[]>(instancesKey, (instances) =>
        instances?.map((instance) =>
          instance.id === state.feature_instance_id && instance.item === state.key && instance.history
            ? { ...instance, state, history: withCheck(instance.history, state.tone) }
            : instance,
        ),
      );
    });
    source.addEventListener("run", (event) => {
      const run = JSON.parse((event as MessageEvent<string>).data) as RunRead;
      void queryClient.invalidateQueries({ queryKey: runsKey });
      if (!run.action_id) return; // A status check, not a button press.
      const lastRun = {
        id: run.id,
        status: run.status,
        started_at: run.started_at,
        finished_at: run.finished_at,
      };
      queryClient.setQueriesData<PadDetail | Pad[]>({ queryKey: padsKey }, (pad) =>
        pad && !Array.isArray(pad)
          ? {
              ...pad,
              buttons: pad.buttons.map((button) =>
                button.action.id === run.action_id &&
                // Events can arrive out of order; an older run never replaces a newer one.
                (!button.last_run || button.last_run.started_at <= run.started_at)
                  ? { ...button, last_run: lastRun }
                  : button,
              ),
            }
          : pad,
      );
    });
    return () => source.close();
  }, [queryClient]);
}
