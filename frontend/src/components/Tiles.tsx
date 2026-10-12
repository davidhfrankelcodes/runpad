import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useFeatureInstances } from "../features";
import { ago } from "../format";
import { fitText, LONG_LABEL } from "../labels";
import { FeatureIcon } from "./FeatureIcon";
import { useCreateTile, type PadDetail, type PadTile } from "../pads";
import { TONE_DOT, TONE_MEANING } from "../tones";
import { Button, ErrorMessage, SelectField, Tooltip } from "./ui";

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

function labelClass(label: string): string {
  // The tile's own text is a step smaller than a button's.
  const size = fitText(label) === "text-base" ? "text-sm" : "text-xs";
  return `line-clamp-2 min-w-0 leading-snug text-soft [overflow-wrap:anywhere] ${size}`;
}

/** A tile's face on the board: what it is, its label, and its State, updated live by
 * useLiveEvents. Fills a board cell, the same size as a button. */
export function TileCard({ tile }: { tile: PadTile }) {
  return (
    <div className="flex h-full w-full min-w-0 flex-col gap-1 overflow-hidden rounded-xl border border-line bg-card p-4">
      <span className="flex items-center gap-1.5 text-xs text-muted">
        <FeatureIcon name={tile.kind.icon} className="h-4 w-4 shrink-0 text-accent" />
        <span className="truncate">{tile.kind.name}</span>
      </span>
      {tile.label.length > LONG_LABEL ? (
        <Tooltip className="flex min-w-0" text={tile.label}>
          <span tabIndex={0} className={labelClass(tile.label)}>
            {tile.label}
          </span>
        </Tooltip>
      ) : (
        <span className={labelClass(tile.label)}>{tile.label}</span>
      )}
      {tile.state ? (
        <>
          <Tooltip
            className="flex min-w-0"
            text={`${TONE_MEANING[tile.state.tone]} Checked ${ago(tile.state.checked_at)}${checkedAgain(tile)}`}
          >
            <span tabIndex={0} className="flex min-w-0 items-center gap-2 text-lg font-medium">
              <span aria-hidden="true" className={`h-2.5 w-2.5 shrink-0 rounded-full ${TONE_DOT[tile.state.tone]}`} />
              <span className="truncate">{tile.state.value}</span>
            </span>
          </Tooltip>
          {tile.state.detail && (
            <span className="line-clamp-1 text-xs text-faint [overflow-wrap:anywhere]">{tile.state.detail}</span>
          )}
        </>
      ) : (
        <Tooltip className="flex" text="Not checked yet. The first check runs within a few seconds.">
          <span tabIndex={0} className="text-lg text-faint">
            checking…
          </span>
        </Tooltip>
      )}
    </div>
  );
}

/** Tiles come from feature instances (the Tiles page); this puts one (back) on the pad. */
export function AddTileForm({ pad }: { pad: PadDetail }) {
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
        name: instance.name,
      })),
    ) ?? [];
  if (options.length === 0) {
    return (
      <p className="text-sm text-muted">
        No tiles yet. Make one on the <Link to="/tiles" className="underline">Tiles</Link> page.
      </p>
    );
  }

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
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <SelectField label="Tile" required value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="" disabled>
          Choose a tile
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
