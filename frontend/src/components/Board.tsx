import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Link } from "react-router";
import { needsDialog, useRunAction, type RunDetail } from "../actions";
import { fitText } from "../labels";
import {
  BUTTON_COLORS,
  boardEntries,
  useDeleteButton,
  useDeleteTile,
  usePads,
  useReorderBoard,
  useUpdateButton,
  useUpdateTile,
  type BoardEntry,
  type ButtonColor,
  type PadButton,
  type PadDetail,
} from "../pads";
import { FeatureIcon } from "./FeatureIcon";
import { RunDialog } from "./RunDialog";
import { KindLine, TileCard } from "./Tiles";
import { Button, Card, ErrorMessage, SelectField, TextField, Tooltip } from "./ui";

/** How long a pressed button stays armed, waiting for the second press. */
const ARMED_MS = 4000;
/** A second press sooner than this is a double tap, not a confirmation, and is ignored. */
const DOUBLE_TAP_MS = 400;

const BUTTON_STYLES: Record<ButtonColor, string> = {
  slate: "bg-zinc-800 hover:bg-zinc-700 border-zinc-600",
  emerald: "bg-emerald-800 hover:bg-emerald-700 border-emerald-600",
  sky: "bg-sky-800 hover:bg-sky-700 border-sky-600",
  amber: "bg-amber-700 hover:bg-amber-600 border-amber-500",
  red: "bg-red-800 hover:bg-red-700 border-red-600",
  violet: "bg-violet-800 hover:bg-violet-700 border-violet-600",
};

// Every card, button or tile, fills one cell of the same size.
const GRID = "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4";
const CELL = "relative flex h-36 min-w-0";

/** What pressing a button does, before it does it. */
function pressHint(button: PadButton): string {
  const { args, confirm, kind } = button.action;
  const names = args.map((arg) => arg.label || arg.name).join(", ");
  const then =
    args.length && confirm
      ? `Asks for ${names}, then for confirmation, before running.`
      : args.length
        ? `Asks for ${names}, then runs.`
        : confirm
          ? "Asks for confirmation, then runs."
          : "Press once to arm, then again within a few seconds to run.";
  // Starts with the full label, which a small button may cut short.
  return `${button.label}. ${kind.name}. ${then}`;
}

/** A button's face: label, type icon, and description (or "Press again to run"). */
function ButtonFace({ button, armed }: { button: PadButton; armed: boolean }) {
  return (
    <>
      <span className="flex w-full items-start justify-between gap-2">
        <span
          className={`line-clamp-2 min-w-0 leading-snug font-medium [overflow-wrap:anywhere] ${fitText(button.label)}`}
        >
          {button.label}
        </span>
        <FeatureIcon name={button.action.kind.icon} className="h-5 w-5 shrink-0 text-white/70" />
      </span>
      {armed ? (
        <span role="status" className="text-sm font-semibold">
          Press again to run
        </span>
      ) : (
        button.action.description && (
          <span className="line-clamp-2 text-xs text-white/70 [overflow-wrap:anywhere]">
            {button.action.description}
          </span>
        )
      )}
    </>
  );
}

const FACE =
  "flex h-full w-full min-w-0 flex-col items-start justify-between overflow-hidden rounded-xl border p-4 text-left text-white";

/** The pad as people use it: press buttons, read tiles. */
export function Board({
  pad,
  admin,
  onStarted,
}: {
  pad: PadDetail;
  admin: boolean;
  onStarted: (run: RunDetail) => void;
}) {
  const run = useRunAction();
  const [asking, setAsking] = useState<PadButton | null>(null);
  // A button without a dialog runs on its second press, so a stray tap does nothing.
  const [armedAt, setArmedAt] = useState<{ id: string; at: number } | null>(null);
  const entries = boardEntries(pad);

  useEffect(() => {
    if (!armedAt) return;
    const timer = setTimeout(() => setArmedAt(null), ARMED_MS);
    return () => clearTimeout(timer);
  }, [armedAt]);

  function press(button: PadButton, at: number) {
    if (needsDialog(button.action)) {
      setArmedAt(null);
      setAsking(button);
    } else if (armedAt?.id !== button.id) {
      setArmedAt({ id: button.id, at });
    } else if (at - armedAt.at >= DOUBLE_TAP_MS) {
      setArmedAt(null);
      run.mutate({ id: button.action.id, args: {} }, { onSuccess: onStarted });
    }
  }

  if (entries.length === 0) {
    return (
      <p className="mt-8 text-center text-faint">
        This pad is empty.{admin && ` Use Edit ${pad.name} to add buttons and tiles.`}
      </p>
    );
  }

  return (
    <>
      <ErrorMessage error={run.error} />
      <ul className={GRID} aria-label="Board">
        {entries.map((entry) => (
          <li key={entry.key} className={CELL}>
            {entry.kind === "tile" ? (
              <TileCard tile={entry.tile} />
            ) : (
              <Tooltip className="flex w-full" text={pressHint(entry.button)}>
                <button
                  type="button"
                  disabled={run.isPending}
                  onClick={(e) => press(entry.button, e.timeStamp)}
                  onKeyDown={(e) => e.key === "Escape" && setArmedAt(null)}
                  className={`${FACE} transition-colors disabled:opacity-60 ${BUTTON_STYLES[entry.button.color]} ${armedAt?.id === entry.button.id ? "ring-4 ring-white" : ""}`}
                >
                  <ButtonFace button={entry.button} armed={armedAt?.id === entry.button.id} />
                </button>
              </Tooltip>
            )}
          </li>
        ))}
      </ul>
      {asking && (
        <RunDialog
          action={asking.action}
          title={asking.label}
          onClose={() => setAsking(null)}
          onStarted={(started) => {
            setAsking(null);
            onStarted(started);
          }}
        />
      )}
    </>
  );
}

function entryLabel(entry: BoardEntry): string {
  return entry.kind === "button" ? entry.button.label : entry.tile.label;
}

/** The pad being arranged: drag cards by their handle, or select one to change it. Every
 * move is saved right away, for everyone. */
export function BoardEditor({ pad }: { pad: PadDetail }) {
  const reorder = useReorderBoard();
  const entries = boardEntries(pad);
  const byKey = new Map(entries.map((entry) => [entry.key, entry]));
  const [selected, setSelected] = useState<string | null>(null);
  // While dragging: the order on screen, and the card being dragged.
  const [draft, setDraft] = useState<string[] | null>(null);
  const dragging = useRef<string | null>(null);
  const draftRef = useRef<string[] | null>(null);
  // The same card, for drawing it faded while it moves.
  const [dragKey, setDragKey] = useState<string | null>(null);

  const keys = draft ?? entries.map((entry) => entry.key);
  const shown = keys.flatMap((key) => {
    const entry = byKey.get(key);
    return entry ? [entry] : [];
  });
  const selectedEntry = selected ? byKey.get(selected) : undefined;

  function save(order: string[]) {
    const before = entries.map((entry) => entry.key);
    if (order.join() !== before.join()) reorder.mutate({ padId: pad.id, keys: order });
  }

  function setDraftOrder(order: string[] | null) {
    draftRef.current = order;
    setDraft(order);
  }

  function startDrag(event: PointerEvent<HTMLButtonElement>, key: string) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragging.current = key;
    setDragKey(key);
    setSelected(key);
    setDraftOrder(entries.map((entry) => entry.key));
  }

  function moveDrag(event: PointerEvent<HTMLButtonElement>) {
    const key = dragging.current;
    const order = draftRef.current;
    if (!key || !order) return;
    const over = document
      .elementsFromPoint(event.clientX, event.clientY)
      .map((element) => (element as HTMLElement).dataset?.boardKey)
      .find((found) => found && found !== key);
    if (!over) return;
    const next = order.filter((k) => k !== key);
    next.splice(next.indexOf(over) + (order.indexOf(over) > order.indexOf(key) ? 1 : 0), 0, key);
    if (next.join() !== order.join()) setDraftOrder(next);
  }

  function endDrag(commit: boolean) {
    const order = draftRef.current;
    dragging.current = null;
    setDragKey(null);
    if (commit && order) save(order);
    setDraftOrder(null);
  }

  function step(key: string, delta: number) {
    const order = entries.map((entry) => entry.key);
    const from = order.indexOf(key);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= order.length) return;
    order.splice(from, 1);
    order.splice(to, 0, key);
    save(order);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">
        Drag a card by its <GripIcon className="inline h-4 w-4 align-text-bottom" /> handle to move
        it, or select it to rename, recolor, or remove it. Changes are saved right away, for
        everyone who uses this pad.
      </p>
      <ErrorMessage error={reorder.error} />
      {shown.length === 0 ? (
        <p className="text-sm text-faint">Nothing on this pad yet. Add a button or a tile below.</p>
      ) : (
        <ul className={GRID} aria-label="Board">
          {shown.map((entry) => {
            const isSelected = selected === entry.key;
            const isDragging = dragKey === entry.key;
            return (
              <li
                key={entry.key}
                data-board-key={entry.key}
                className={`${CELL} rounded-xl ${isSelected ? "ring-2 ring-accent ring-offset-2 ring-offset-transparent" : ""} ${isDragging ? "opacity-50" : ""}`}
              >
                <button
                  type="button"
                  aria-pressed={isSelected}
                  aria-label={`Select ${entryLabel(entry)}`}
                  onClick={() => setSelected(isSelected ? null : entry.key)}
                  className="flex h-full w-full min-w-0 text-left"
                >
                  {entry.kind === "tile" ? (
                    <span className="pointer-events-none flex h-full w-full min-w-0">
                      <TileCard tile={entry.tile} />
                    </span>
                  ) : (
                    <span className={`${FACE} ${BUTTON_STYLES[entry.button.color]}`}>
                      <ButtonFace button={entry.button} armed={false} />
                    </span>
                  )}
                </button>
                <span className="absolute right-1.5 bottom-1.5 flex">
                  <Tooltip text="Drag to move this card.">
                    <button
                    type="button"
                    aria-label={`Drag ${entryLabel(entry)}`}
                    onPointerDown={(e) => startDrag(e, entry.key)}
                    onPointerMove={moveDrag}
                    onPointerUp={() => endDrag(true)}
                    onPointerCancel={() => endDrag(false)}
                    className="flex cursor-grab touch-none items-center justify-center rounded-md bg-black/50 p-1.5 text-white hover:bg-black/70 active:cursor-grabbing"
                  >
                      <GripIcon className="h-4 w-4" />
                    </button>
                  </Tooltip>
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {selectedEntry && (
        <SelectedCard
          key={selectedEntry.key}
          entry={selectedEntry}
          first={keys[0] === selectedEntry.key}
          last={keys[keys.length - 1] === selectedEntry.key}
          onStep={(delta) => step(selectedEntry.key, delta)}
          onRemoved={() => setSelected(null)}
        />
      )}
    </div>
  );
}

/** Six dots: a drag handle. */
function GripIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className} fill="currentColor">
      {[6, 12, 18].flatMap((y) =>
        [9, 15].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r={1.6} />),
      )}
    </svg>
  );
}

/** Settings of the selected card: its label, color (buttons), pad, place, or removal. */
function SelectedCard({
  entry,
  first,
  last,
  onStep,
  onRemoved,
}: {
  entry: BoardEntry;
  first: boolean;
  last: boolean;
  onStep: (delta: number) => void;
  onRemoved: () => void;
}) {
  const updateButton = useUpdateButton();
  const updateTile = useUpdateTile();
  const removeButton = useDeleteButton();
  const removeTile = useDeleteTile();
  const pads = usePads();
  const isButton = entry.kind === "button";
  const id = isButton ? entry.button.id : entry.tile.id;
  const padId = isButton ? entry.button.pad_id : entry.tile.pad_id;
  const kind = isButton ? entry.button.action.kind : entry.tile.kind;
  const [label, setLabel] = useState(entryLabel(entry));

  function update(changes: { label?: string; pad_id?: string; color?: ButtonColor }) {
    if (isButton) updateButton.mutate({ id, ...changes });
    else updateTile.mutate({ id, label: changes.label, pad_id: changes.pad_id });
  }

  function remove() {
    const options = { onSuccess: onRemoved };
    if (isButton) removeButton.mutate(id, options);
    else removeTile.mutate(id, options);
  }

  const source = isButton
    ? { to: `/actions/${entry.button.action.id}`, text: "Edit command", tip: "The action this button runs. Shared by every button for it." }
    : {
        to: `/features/instances/${entry.tile.feature_instance_id}`,
        text: "Edit tile settings",
        tip: "What this tile checks. Shared by every place the tile is shown.",
      };

  return (
    <Card title={isButton ? "Selected button" : "Selected tile"}>
      <div className="flex flex-col gap-3">
        <KindLine kind={kind} />
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-40 flex-1">
            <TextField
              label="Label"
              value={label}
              maxLength={64}
              onChange={(e) => setLabel(e.target.value)}
              onBlur={() => label && label !== entryLabel(entry) && update({ label })}
            />
          </div>
          {isButton && (
            <SelectField
              label="Color"
              value={entry.button.color}
              onChange={(e) => update({ color: e.target.value as ButtonColor })}
            >
              {BUTTON_COLORS.map((color) => (
                <option key={color} value={color}>
                  {color}
                </option>
              ))}
            </SelectField>
          )}
          {pads.data && pads.data.length > 1 && (
            <SelectField
              label="Pad"
              value={padId}
              onChange={(e) => {
                update({ pad_id: e.target.value });
                onRemoved();
              }}
            >
              {pads.data.map((pad) => (
                <option key={pad.id} value={pad.id}>
                  {pad.name}
                </option>
              ))}
            </SelectField>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" disabled={first} onClick={() => onStep(-1)} tooltip="Move it one place earlier on the board.">
            ← Earlier
          </Button>
          <Button variant="secondary" disabled={last} onClick={() => onStep(1)} tooltip="Move it one place later on the board.">
            Later →
          </Button>
          <Link to={source.to}>
            <Button variant="secondary" tooltip={source.tip}>
              {source.text}
            </Button>
          </Link>
          <Button
            variant="danger"
            onClick={remove}
            tooltip={
              isButton
                ? "Remove the button from this pad. The action and its run history are kept."
                : "Remove the tile from this pad. The tile itself is kept on the Tiles page."
            }
          >
            Remove from pad
          </Button>
        </div>
        <ErrorMessage
          error={updateButton.error ?? updateTile.error ?? removeButton.error ?? removeTile.error}
        />
      </div>
    </Card>
  );
}
