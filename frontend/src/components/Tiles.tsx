import { useState, type FormEvent } from "react";
import { useFeatureInstances } from "../features";
import { ago } from "../format";
import { FeatureIcon } from "./FeatureIcon";
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
import { Button, Card, ErrorMessage, SelectField, TextField, Tooltip } from "./ui";

const TONE_MEANING: Record<TileState["tone"], string> = {
  good: "Green: as it should be.",
  warn: "Amber: working, but needs attention soon, such as a disk filling up.",
  bad: "Red: stopped, down, or missing.",
  neutral: "Blue: in between, such as starting or partly up.",
  unknown: "Grey: the last check could not tell.",
};

const TONE_DOT: Record<TileState["tone"], string> = {
  good: "bg-emerald-400",
  warn: "bg-amber-400",
  bad: "bg-red-500",
  neutral: "bg-sky-400",
  unknown: "bg-zinc-500",
};

/** "every 10 minutes", from a check interval in seconds. */
function every(seconds: number): string {
  if (seconds % 3600 === 0) return seconds === 3600 ? "every hour" : `every ${seconds / 3600} hours`;
  if (seconds % 60 === 0) return seconds === 60 ? "every minute" : `every ${seconds / 60} minutes`;
  return `every ${seconds} seconds`;
}

function checkedAgain(tile: PadTile): string {
  return tile.check_interval_seconds
    ? `; checked again ${every(tile.check_interval_seconds)} and after its buttons run.`
    : ".";
}

/** Read-only tiles showing each State, updated live by useLiveEvents. */
export function TileGrid({ tiles }: { tiles: PadTile[] }) {
  if (tiles.length === 0) return null;
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4" aria-label="Status">
      {tiles.map((tile) => (
        <li
          key={tile.id}
          className="flex min-h-20 flex-col gap-1 rounded-xl border border-line bg-card p-4"
        >
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <FeatureIcon name={tile.kind.icon} className="h-4 w-4 shrink-0 text-accent" />
            <span className="truncate">{tile.kind.name}</span>
          </span>
          <span className="truncate text-sm text-soft">{tile.label}</span>
          {tile.state ? (
            <>
              <Tooltip
                className="flex"
                text={`${TONE_MEANING[tile.state.tone]} Checked ${ago(tile.state.checked_at)}${checkedAgain(tile)}`}
              >
                <span tabIndex={0} className="flex items-center gap-2 text-lg font-medium">
                  <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${TONE_DOT[tile.state.tone]}`} />
                  {tile.state.value}
                </span>
              </Tooltip>
              {tile.state.detail && (
                <span className="line-clamp-2 text-xs text-faint">{tile.state.detail}</span>
              )}
            </>
          ) : (
            <Tooltip className="flex" text="Not checked yet. The first check runs within a few seconds.">
              <span tabIndex={0} className="text-lg text-faint">
                checking…
              </span>
            </Tooltip>
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
          <p className="text-sm text-faint">
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
    <div className="flex flex-col gap-2 rounded-md border border-line p-3">
      <KindLine kind={tile.kind} />
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1">
          <TextField
            label="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onBlur={() => label && label !== tile.label && update.mutate({ id: tile.id, label })}
          />
        </div>
        <Button variant="secondary" disabled={first} onClick={() => onMove(-1)} aria-label="Move earlier" tooltip="Move this tile earlier on the pad.">
          ↑
        </Button>
        <Button variant="secondary" disabled={last} onClick={() => onMove(1)} aria-label="Move later" tooltip="Move this tile later on the pad.">
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
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => remove.mutate(tile.id)}
          tooltip="Remove the tile from this pad. You can add it back below."
        >
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

/** The type of a pad item ("Ping check", "Custom command"), with its icon. */
export function KindLine({ kind }: { kind: PadTile["kind"] }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted">
      <FeatureIcon name={kind.icon} className="h-4 w-4 shrink-0 text-accent" />
      {kind.name}
    </span>
  );
}
