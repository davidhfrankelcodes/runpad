import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router";
import { useActions } from "../actions";
import { useCurrentUser } from "../auth";
import { Board, BoardEditor } from "../components/Board";
import { RunOutput } from "../components/RunOutput";
import { AddTileForm } from "../components/Tiles";
import {
  Button,
  Card,
  CloseLabel,
  ErrorMessage,
  FormActions,
  SelectField,
  TextField,
  Tooltip,
} from "../components/ui";
import {
  useCreateButton,
  useDeletePad,
  usePad,
  usePads,
  useReorderPads,
  useUpdatePad,
  type PadDetail,
} from "../pads";
import { useUsers } from "../users";
import { NewPadForm } from "./PadsPage";

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
          <div className="flex shrink-0 items-center justify-end gap-3 sm:pb-2">
            {editing ? (
              <>
                <span className="text-sm text-muted">Changes are saved as you make them.</span>
                <Button tooltip="Finish editing, back to pressing buttons." onClick={() => setEditing(false)}>
                  Done
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="secondary"
                  disabled={creating}
                  tooltip="Add another pad, a new page of buttons and tiles."
                  onClick={() => setCreating(true)}
                >
                  New pad
                </Button>
                <Button
                  variant="secondary"
                  tooltip={`Arrange ${name}: drag buttons and tiles around, rename, recolor, add, or remove them.`}
                  onClick={() => {
                    setCreating(false);
                    setEditing(true);
                  }}
                >
                  <span className="block max-w-48 truncate">Edit {name}</span>
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      {creating && (
        <div className="w-full max-w-md self-end">
          <NewPadForm onCreated={() => setCreating(false)} onCancel={() => setCreating(false)} />
        </div>
      )}
      <ErrorMessage error={pad.error} />
      {pad.data &&
        (editing ? (
          <PadEditor pad={pad.data} />
        ) : (
          <Board
            pad={pad.data}
            admin={user.role === "admin"}
            onStarted={(run) => setRunId(run.id)}
          />
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

function PadEditor({ pad }: { pad: PadDetail }) {
  return (
    <div className="flex flex-col gap-6">
      <BoardEditor pad={pad} />
      <AddButtonForm pad={pad} />
      <Card
        title="Add a tile"
        actions={
          <Link to={`/features?kind=tile&pad=${pad.id}`}>
            <Button variant="secondary" tooltip="Pick what a new tile checks from the catalog, then fill in a short form.">
              New tile
            </Button>
          </Link>
        }
      >
        <AddTileForm pad={pad} />
      </Card>
      <PadSettings pad={pad} />
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
    <Card
      title="Add a button"
      actions={
        <Link to={`/actions/new?pad=${pad.id}`}>
          <Button variant="secondary" tooltip="Write a new command, and put a button for it on this pad.">
            New custom button
          </Button>
        </Link>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">For an existing action:</p>
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
  // Shown at once; put back if saving fails.
  const [memberIds, setMemberIds] = useState(pad.member_ids);
  const members = users.data?.filter((u) => u.role === "member") ?? [];

  // Saved as they change, like the board above.
  function rename() {
    const next = name.trim();
    if (next && next !== pad.name) update.mutate({ id: pad.id, name: next });
    else setName(pad.name);
  }

  function toggle(id: string, on: boolean) {
    const next = on ? [...memberIds, id] : memberIds.filter((m) => m !== id);
    setMemberIds(next);
    update.mutate({ id: pad.id, member_ids: next }, { onError: () => setMemberIds(pad.member_ids) });
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
      <div className="flex flex-col gap-4">
        <TextField
          label="Name"
          required
          maxLength={64}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={rename}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
        />
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
                tooltip="Move this pad one tab to the left."
              >
                ← Move left
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={index < 0 || index >= ids.length - 1 || reorder.isPending}
                onClick={() => move(1)}
                tooltip="Move this pad one tab to the right."
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
        <FormActions
          start={
            <Button
              type="button"
              variant="danger"
              onClick={confirmDelete}
              tooltip="Delete this pad with its buttons and tiles. Actions and run history are kept."
            >
              Delete pad
            </Button>
          }
        />
      </div>
    </Card>
  );
}
