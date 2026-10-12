import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router";
import { needsDialog, useActions, useRunAction, type RunDetail } from "../actions";
import { useCurrentUser } from "../auth";
import { FeatureIcon } from "../components/FeatureIcon";
import { RunDialog } from "../components/RunDialog";
import { RunOutput } from "../components/RunOutput";
import { KindLine, TileGrid, TilesEditor } from "../components/Tiles";
import { fitText } from "../labels";
import { Button, Card, CloseLabel, ErrorMessage, SelectField, TextField, Tooltip } from "../components/ui";
import {
  BUTTON_COLORS,
  useCreateButton,
  useDeleteButton,
  useDeletePad,
  usePad,
  usePads,
  useReorderButtons,
  useReorderPads,
  useUpdateButton,
  useUpdatePad,
  type ButtonColor,
  type PadButton,
  type PadDetail,
} from "../pads";
import { useUsers } from "../users";
import { NewPadForm } from "./PadsPage";

/** How long a pressed button stays armed, waiting for the second press. */
const ARMED_MS = 4000;
/** A second press sooner than this is a double tap, not a confirmation, and is ignored. */
const DOUBLE_TAP_MS = 400;

const TILE_COLORS: Record<ButtonColor, string> = {
  slate: "bg-zinc-800 hover:bg-zinc-700 border-zinc-600",
  emerald: "bg-emerald-800 hover:bg-emerald-700 border-emerald-600",
  sky: "bg-sky-800 hover:bg-sky-700 border-sky-600",
  amber: "bg-amber-700 hover:bg-amber-600 border-amber-500",
  red: "bg-red-800 hover:bg-red-700 border-red-600",
  violet: "bg-violet-800 hover:bg-violet-700 border-violet-600",
};

export default function PadPage() {
  const { id = "" } = useParams();
  // Keyed so edit mode and the run panel reset when switching pads.
  return <PadView key={id} id={id} />;
}

function PadView({ id }: { id: string }) {
  const pad = usePad(id);
  const user = useCurrentUser();
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);
  const name = pad.data?.name ?? "pad";

  // Escape hides the output panel, unless a dialog is open on top of it.
  useEffect(() => {
    if (!runId) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !document.querySelector('[role="dialog"]')) setRunId(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [runId]);

  return (
    <div className="flex flex-col gap-6">
      {/* Pad tabs sit on the border; on phones the buttons go above them. */}
      <div className="flex flex-col-reverse gap-2 border-b border-line sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <PadTabs />
        {user.role === "admin" && (
          <div className="flex shrink-0 justify-end gap-2 sm:pb-2">
            <Button
              variant="secondary"
              tooltip="Add another pad, a new page of buttons and tiles."
              onClick={() => setCreating(!creating)}
            >
              {creating ? "Cancel" : "New pad"}
            </Button>
            <Button
              variant={editing ? "primary" : "secondary"}
              tooltip={
                editing
                  ? "Back to pressing buttons."
                  : `Rename, reorder, move, add, or remove the buttons and tiles on ${name}.`
              }
              onClick={() => setEditing(!editing)}
            >
              <span className="block max-w-48 truncate">{editing ? "Done" : `Edit ${name}`}</span>
            </Button>
          </div>
        )}
      </div>
      {creating && (
        <div className="w-full max-w-md self-end">
          <NewPadForm onCreated={() => setCreating(false)} />
        </div>
      )}
      <ErrorMessage error={pad.error} />
      {pad.data &&
        (editing ? (
          <PadEditor pad={pad.data} />
        ) : (
          <>
            <TileGrid tiles={pad.data.tiles} />
            <ButtonGrid
              pad={pad.data}
              admin={user.role === "admin"}
              onStarted={(run) => setRunId(run.id)}
            />
          </>
        ))}
      {/* Room to scroll everything above the output panel, which is fixed over the page. */}
      {runId && <div aria-hidden="true" className="h-96 shrink-0" />}
      {runId && (
        <div className="fixed inset-x-0 bottom-0 z-10 border-t border-line-strong bg-card p-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur-md">
          <div className="mx-auto flex max-w-5xl flex-col gap-2">
            <div className="flex items-center justify-end gap-3 text-sm">
              <Tooltip text="This run's own page, with its full output and details.">
                <Link to={`/runs/${runId}`} className="text-muted underline">
                  Open
                </Link>
              </Tooltip>
              <Button
                variant="secondary"
                onClick={() => setRunId(null)}
                tooltip="Hide this output (or press Escape). The run keeps going; it stays in Runs."
              >
                <CloseLabel />
              </Button>
            </div>
            <RunOutput key={runId} id={runId} compact onRerun={(run) => setRunId(run.id)} />
          </div>
        </div>
      )}
    </div>
  );
}

function PadTabs() {
  const pads = usePads();
  return (
    <nav aria-label="Pads" className="-mb-px flex flex-wrap">
      {pads.data?.map((pad) => (
        <NavLink
          key={pad.id}
          to={`/pads/${pad.id}`}
          className={({ isActive }) =>
            `border-b-2 px-3 py-2 text-sm ${isActive ? "border-accent font-medium text-fg-hover" : "border-transparent text-muted hover:text-fg-hover"}`
          }
        >
          {pad.name}
        </NavLink>
      ))}
    </nav>
  );
}

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

function ButtonGrid({
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
  const armed = armedAt?.id ?? null;

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

  if (pad.buttons.length === 0) {
    return pad.tiles.length === 0 ? (
      <p className="mt-8 text-center text-faint">
        This pad has no buttons yet.{admin && ` Use Edit ${pad.name} to add some.`}
      </p>
    ) : null;
  }

  return (
    <>
      <ErrorMessage error={run.error} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {pad.buttons.map((button) => (
          <Tooltip key={button.id} className="flex" text={pressHint(button)}>
            <button
              type="button"
              disabled={run.isPending}
              onClick={(e) => press(button, e.timeStamp)}
              onKeyDown={(e) => e.key === "Escape" && setArmedAt(null)}
              className={`flex min-h-24 flex-col items-start justify-between w-full rounded-xl border p-4 text-left text-white transition-colors disabled:opacity-60 ${TILE_COLORS[button.color]} ${armed === button.id ? "ring-4 ring-white" : ""}`}
            >
              <span className="flex w-full items-start justify-between gap-2">
                <span
                  className={`line-clamp-3 min-w-0 leading-snug font-medium [overflow-wrap:anywhere] ${fitText(button.label)}`}
                >
                  {button.label}
                </span>
                <FeatureIcon name={button.action.kind.icon} className="h-5 w-5 shrink-0 text-white/70" />
              </span>
              {armed === button.id ? (
                <span role="status" className="text-sm font-semibold">
                  Press again to run
                </span>
              ) : (
                button.action.description && (
                  <span className="line-clamp-2 text-xs text-white/70 [overflow-wrap:anywhere]">{button.action.description}</span>
                )
              )}
            </button>
          </Tooltip>
        ))}
      </div>
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

function PadEditor({ pad }: { pad: PadDetail }) {
  const reorder = useReorderButtons();

  function move(index: number, delta: number) {
    const ids = pad.buttons.map((b) => b.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target] as string, ids[index] as string];
    reorder.mutate({ padId: pad.id, ids });
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="Buttons">
        <div className="flex flex-col gap-2">
          {pad.buttons.length === 0 && <p className="text-sm text-faint">No buttons yet.</p>}
          {pad.buttons.map((button, index) => (
            <ButtonRow
              key={button.id}
              button={button}
              first={index === 0}
              last={index === pad.buttons.length - 1}
              onMove={(delta) => move(index, delta)}
            />
          ))}
          <ErrorMessage error={reorder.error} />
        </div>
      </Card>
      <AddButtonForm pad={pad} />
      <TilesEditor pad={pad} />
      <PadSettings pad={pad} />
    </div>
  );
}

function ButtonRow({
  button,
  first,
  last,
  onMove,
}: {
  button: PadButton;
  first: boolean;
  last: boolean;
  onMove: (delta: number) => void;
}) {
  const update = useUpdateButton();
  const remove = useDeleteButton();
  const pads = usePads();
  const [label, setLabel] = useState(button.label);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-line p-3">
      <KindLine kind={button.action.kind} />
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-40 flex-1">
          <TextField
            label="Label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onBlur={() => label !== button.label && update.mutate({ id: button.id, label })}
          />
        </div>
        <SelectField
          label="Color"
          value={button.color}
          onChange={(e) => update.mutate({ id: button.id, color: e.target.value as ButtonColor })}
        >
          {BUTTON_COLORS.map((color) => (
            <option key={color} value={color}>
              {color}
            </option>
          ))}
        </SelectField>
        <Button variant="secondary" disabled={first} onClick={() => onMove(-1)} aria-label="Move earlier" tooltip="Move this button earlier on the pad.">
          ↑
        </Button>
        <Button variant="secondary" disabled={last} onClick={() => onMove(1)} aria-label="Move later" tooltip="Move this button later on the pad.">
          ↓
        </Button>
        {pads.data && pads.data.length > 1 && (
          <SelectField
            label="Pad"
            value={button.pad_id}
            onChange={(e) => update.mutate({ id: button.id, pad_id: e.target.value })}
          >
            {pads.data.map((pad) => (
              <option key={pad.id} value={pad.id}>
                {pad.name}
              </option>
            ))}
          </SelectField>
        )}
        <Link to={`/actions/${button.action.id}`}>
          <Button
            variant="secondary"
            tooltip="The command this button runs. Shared by every button for the same action."
          >
            Edit command
          </Button>
        </Link>
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => remove.mutate(button.id)}
          tooltip="Remove the button from this pad. The action and its run history are kept."
        >
          Remove
        </Button>
      </div>
      <ErrorMessage error={update.error ?? remove.error} />
    </div>
  );
}

function AddButtonForm({ pad }: { pad: PadDetail }) {
  const actions = useActions();
  const create = useCreateButton();
  const [actionId, setActionId] = useState("");
  const [label, setLabel] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const action = actions.data?.find((a) => a.id === actionId);
    create.mutate(
      { padId: pad.id, action_id: actionId, label: label || (action?.name ?? "Button") },
      {
        onSuccess: () => {
          setActionId("");
          setLabel("");
        },
      },
    );
  }

  return (
    <Card title="Add a button">
      <div className="flex flex-col gap-4">
        <Link to={`/actions/new?pad=${pad.id}`}>
          <Button type="button" tooltip="Write a new command, and put a button for it on this pad.">
            New custom button
          </Button>
        </Link>
        <p className="text-sm text-muted">Or add a button for an existing action:</p>
        <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
          <SelectField
            label="Action"
            required
            value={actionId}
            onChange={(e) => setActionId(e.target.value)}
          >
            <option value="" disabled>
              Choose an action
            </option>
            {actions.data?.map((action) => (
              <option key={action.id} value={action.id}>
                {action.name}
              </option>
            ))}
          </SelectField>
          <TextField
            label="Label (defaults to the action name)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <Button type="submit" variant="secondary" disabled={create.isPending}>
            Add
          </Button>
        </form>
        <ErrorMessage error={create.error ?? actions.error} />
      </div>
    </Card>
  );
}

function PadSettings({ pad }: { pad: PadDetail }) {
  const update = useUpdatePad();
  const remove = useDeletePad();
  const pads = usePads();
  const reorder = useReorderPads();
  const ids = pads.data?.map((p) => p.id) ?? [];
  const index = ids.indexOf(pad.id);
  const users = useUsers();
  const navigate = useNavigate();
  const [name, setName] = useState(pad.name);
  const [memberIds, setMemberIds] = useState<string[]>(pad.member_ids);
  const members = users.data?.filter((u) => u.role === "member") ?? [];

  function toggle(id: string, on: boolean) {
    setMemberIds((current) => (on ? [...current, id] : current.filter((m) => m !== id)));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate({ id: pad.id, name, member_ids: memberIds });
  }

  function move(delta: number) {
    const target = index + delta;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const order = [...ids];
    [order[index], order[target]] = [order[target] as string, order[index] as string];
    reorder.mutate(order);
  }

  function confirmDelete() {
    if (window.confirm(`Delete pad "${pad.name}" and its buttons? The actions are kept.`)) {
      remove.mutate(pad.id, { onSuccess: () => void navigate("/") });
    }
  }

  return (
    <Card title="Pad settings">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        {ids.length > 1 && (
          <div className="flex flex-col gap-1 text-sm">
            <span className="text-soft">
              Position: {index + 1} of {ids.length}
            </span>
            <span className="text-xs text-faint">
              Tabs are in this order for everyone. The first pad someone can see opens when they
              log in or select the logo.
            </span>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={index <= 0 || reorder.isPending}
                onClick={() => move(-1)}
                tooltip="Move this pad one tab to the left. Saved right away."
              >
                ← Move left
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={index < 0 || index >= ids.length - 1 || reorder.isPending}
                onClick={() => move(1)}
                tooltip="Move this pad one tab to the right. Saved right away."
              >
                Move right →
              </Button>
            </div>
          </div>
        )}
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1 text-soft">Members who can see this pad and press its buttons</legend>
          {members.length === 0 && (
            <p className="text-faint">
              No members yet. Add them on the <Link to="/users" className="underline">Users</Link>{" "}
              page. Admins always see every pad.
            </p>
          )}
          {members.map((member) => (
            <label key={member.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={memberIds.includes(member.id)}
                onChange={(e) => toggle(member.id, e.target.checked)}
              />
              {member.username}
              {!member.is_active && <span className="text-faint">(deactivated)</span>}
            </label>
          ))}
        </fieldset>
        <ErrorMessage error={update.error ?? remove.error ?? reorder.error} />
        {update.isSuccess && <p className="text-sm text-link">Saved.</p>}
        <div className="flex justify-between">
          <Button type="submit" disabled={update.isPending}>
            Save
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={confirmDelete}
            tooltip="Delete this pad with its buttons and tiles. Actions and run history are kept."
          >
            Delete pad
          </Button>
        </div>
      </form>
    </Card>
  );
}
