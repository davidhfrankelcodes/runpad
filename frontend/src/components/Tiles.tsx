import { useState, type FormEvent } from "react";
import { useFeatureInstances } from "../features";
import { ago } from "../format";
import {
  useCreateTile,
  useDeleteTile,
  usePads,
  useReorderTiles,
  useUpdateTile,
  type PadDetail,
  type PadTile,
  type TileState,
} from "../pads";
import { Button, Card, ErrorMessage, SelectField, TextField } from "./ui";

const TONE_DOT: Record<TileState["tone"], string> = {
  good: "bg-emerald-400",
  bad: "bg-red-500",
  neutral: "bg-sky-400",
  unknown: "bg-zinc-500",
};

/** Read-only tiles showing each State, updated live by useLiveEvents. */
export function TileGrid({ tiles }: { tiles: PadTile[] }) {
  if (tiles.length === 0) return null;
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4" aria-label="Status">
      {tiles.map((tile) => (
        <li
          key={tile.id}
          className="flex min-h-20 flex-col gap-1 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4"
          title={tile.state ? `Checked ${ago(tile.state.checked_at)}` : undefined}
        >
          <span className="truncate text-sm text-zinc-400">{tile.label}</span>
          {tile.state ? (
            <>
              <span className="flex items-center gap-2 text-lg font-medium">
                <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${TONE_DOT[tile.state.tone]}`} />
                {tile.state.value}
              </span>
              {tile.state.detail && (
                <span className="line-clamp-2 text-xs text-zinc-500">{tile.state.detail}</span>
              )}
            </>
          ) : (
            <span className="text-lg text-zinc-500">checking…</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function TilesEditor({ pad }: { pad: PadDetail }) {
  const reorder = useReorderTiles();

  function move(index: number, delta: number) {
    const ids = pad.tiles.map((t) => t.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target] as string, ids[index] as string];
    reorder.mutate({ padId: pad.id, ids });
  }

  return (
    <Card title="Tiles">
      <div className="flex flex-col gap-2">
        {pad.tiles.length === 0 && (
          <p className="text-sm text-zinc-500">
            No tiles. Features that report state, like Docker container, add one when enabled.
          </p>
        )}
        {pad.tiles.map((tile, index) => (
          <TileRow
            key={tile.id}
            tile={tile}
            first={index === 0}
            last={index === pad.tiles.length - 1}
            onMove={(delta) => move(index, delta)}
          />
        ))}
        <ErrorMessage error={reorder.error} />
        <AddTileForm pad={pad} />
      </div>
    </Card>
  );
}

function TileRow({
  tile,
  first,
  last,
  onMove,
}: {
  tile: PadTile;
  first: boolean;
  last: boolean;
  onMove: (delta: number) => void;
}) {
  const update = useUpdateTile();
  const remove = useDeleteTile();
  const pads = usePads();
  const [label, setLabel] = useState(tile.label);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-zinc-800 p-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1">
          <TextField
            label="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onBlur={() => label && label !== tile.label && update.mutate({ id: tile.id, label })}
          />
        </div>
        <Button variant="secondary" disabled={first} onClick={() => onMove(-1)} aria-label="Move earlier">
          ↑
        </Button>
        <Button variant="secondary" disabled={last} onClick={() => onMove(1)} aria-label="Move later">
          ↓
        </Button>
        {pads.data && pads.data.length > 1 && (
          <SelectField
            label="Pad"
            value={tile.pad_id}
            onChange={(e) => update.mutate({ id: tile.id, pad_id: e.target.value })}
          >
            {pads.data.map((pad) => (
              <option key={pad.id} value={pad.id}>
                {pad.name}
              </option>
            ))}
          </SelectField>
        )}
        <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(tile.id)}>
          Remove
        </Button>
      </div>
      <ErrorMessage error={update.error ?? remove.error} />
    </div>
  );
}

/** Tiles come from feature instances; this puts one (back) on the pad. */
function AddTileForm({ pad }: { pad: PadDetail }) {
  const instances = useFeatureInstances();
  const create = useCreateTile();
  const [choice, setChoice] = useState("");
  const options =
    instances.data?.flatMap((instance) =>
      instance.tiles.map((tile) => ({
        value: `${instance.id}/${tile.state_key}`,
        instanceId: instance.id,
        stateKey: tile.state_key,
        label: tile.label,
        name: `${instance.name}: ${tile.label}`,
      })),
    ) ?? [];
  if (options.length === 0) return null;

  function submit(event: FormEvent) {
    event.preventDefault();
    const option = options.find((o) => o.value === choice);
    if (!option) return;
    create.mutate(
      {
        padId: pad.id,
        feature_instance_id: option.instanceId,
        state_key: option.stateKey,
        label: option.label,
      },
      { onSuccess: () => setChoice("") },
    );
  }

  return (
    <form onSubmit={submit} className="mt-2 flex flex-wrap items-end gap-3">
      <SelectField label="Add a tile" required value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="" disabled>
          Choose a state
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.name}
          </option>
        ))}
      </SelectField>
      <Button type="submit" variant="secondary" disabled={create.isPending}>
        Add
      </Button>
      <ErrorMessage error={create.error ?? instances.error} />
    </form>
  );
}
