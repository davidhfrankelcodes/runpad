import { useState, type FormEvent } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router";
import { needsDialog, useActions, useRunAction, type RunDetail } from "../actions";
import { useCurrentUser } from "../auth";
import { RunDialog } from "../components/RunDialog";
import { RunOutput } from "../components/RunOutput";
import { Button, Card, ErrorMessage, SelectField, TextField } from "../components/ui";
import {
  BUTTON_COLORS,
  useCreateButton,
  useDeleteButton,
  useDeletePad,
  usePad,
  usePads,
  useReorderButtons,
  useUpdateButton,
  useUpdatePad,
  type ButtonColor,
  type PadButton,
  type PadDetail,
} from "../pads";
import { useUsers } from "../users";
import { NewPadForm } from "./PadsPage";

const TILE_COLORS: Record<ButtonColor, string> = {
  slate: "bg-zinc-800 hover:bg-zinc-700 border-zinc-700",
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
  const [runId, setRunId] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <PadTabs />
        {user.role === "admin" && (
          <Button variant={editing ? "primary" : "secondary"} onClick={() => setEditing(!editing)}>
            {editing ? "Done" : "Edit pad"}
          </Button>
        )}
      </div>
      <ErrorMessage error={pad.error} />
      {pad.data &&
        (editing ? (
          <PadEditor pad={pad.data} />
        ) : (
          <ButtonGrid pad={pad.data} onStarted={(run) => setRunId(run.id)} />
        ))}
      {runId && (
        <div className="fixed inset-x-0 bottom-0 z-10 border-t border-zinc-700 bg-zinc-950/95 p-4 backdrop-blur">
          <div className="mx-auto flex max-w-5xl flex-col gap-2">
            <div className="flex justify-end gap-3 text-sm">
              <Link to={`/runs/${runId}`} className="text-zinc-400 underline">
                Open
              </Link>
              <button type="button" className="text-zinc-400 hover:text-white" onClick={() => setRunId(null)}>
                Close
              </button>
            </div>
            <RunOutput key={runId} id={runId} compact />
          </div>
        </div>
      )}
    </div>
  );
}

function PadTabs() {
  const pads = usePads();
  return (
    <nav className="flex flex-wrap gap-1">
      {pads.data?.map((pad) => (
        <NavLink
          key={pad.id}
          to={`/pads/${pad.id}`}
          className={({ isActive }) =>
            `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"}`
          }
        >
          {pad.name}
        </NavLink>
      ))}
    </nav>
  );
}

function ButtonGrid({ pad, onStarted }: { pad: PadDetail; onStarted: (run: RunDetail) => void }) {
  const run = useRunAction();
  const [asking, setAsking] = useState<PadButton | null>(null);

  function press(button: PadButton) {
    if (needsDialog(button.action)) {
      setAsking(button);
    } else {
      run.mutate({ id: button.action.id, args: {} }, { onSuccess: onStarted });
    }
  }

  if (pad.buttons.length === 0) {
    return <p className="mt-8 text-center text-zinc-500">This pad has no buttons yet.</p>;
  }

  return (
    <>
      <ErrorMessage error={run.error} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {pad.buttons.map((button) => (
          <button
            key={button.id}
            type="button"
            disabled={run.isPending}
            onClick={() => press(button)}
            className={`flex min-h-24 flex-col items-start justify-between rounded-xl border p-4 text-left transition-colors disabled:opacity-60 ${TILE_COLORS[button.color]}`}
          >
            <span className="text-base font-medium">{button.label}</span>
            {button.action.description && (
              <span className="line-clamp-2 text-xs text-white/70">{button.action.description}</span>
            )}
          </button>
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
          {pad.buttons.length === 0 && <p className="text-sm text-zinc-500">No buttons yet.</p>}
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
      <PadSettings pad={pad} />
      <NewPadForm />
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
  const [label, setLabel] = useState(button.label);

  return (
    <div className="flex flex-col gap-2 rounded-md border border-zinc-800 p-3">
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
        <Button variant="secondary" disabled={first} onClick={() => onMove(-1)} aria-label="Move earlier">
          ↑
        </Button>
        <Button variant="secondary" disabled={last} onClick={() => onMove(1)} aria-label="Move later">
          ↓
        </Button>
        <Link to={`/actions/${button.action.id}`}>
          <Button variant="secondary">Edit command</Button>
        </Link>
        <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(button.id)}>
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
          <Button type="button">New custom button</Button>
        </Link>
        <p className="text-sm text-zinc-400">Or add a button for an existing action:</p>
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

  function confirmDelete() {
    if (window.confirm(`Delete pad "${pad.name}" and its buttons? The actions are kept.`)) {
      remove.mutate(pad.id, { onSuccess: () => void navigate("/") });
    }
  }

  return (
    <Card title="Pad settings">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1 text-zinc-300">Members who can see this pad and press its buttons</legend>
          {members.length === 0 && (
            <p className="text-zinc-500">
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
              {!member.is_active && <span className="text-zinc-500">(deactivated)</span>}
            </label>
          ))}
        </fieldset>
        <ErrorMessage error={update.error ?? remove.error} />
        {update.isSuccess && <p className="text-sm text-emerald-400">Saved.</p>}
        <div className="flex justify-between">
          <Button type="submit" disabled={update.isPending}>
            Save
          </Button>
          <Button type="button" variant="danger" onClick={confirmDelete}>
            Delete pad
          </Button>
        </div>
      </form>
    </Card>
  );
}
