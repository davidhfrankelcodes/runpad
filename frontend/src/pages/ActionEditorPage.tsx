import { Fragment, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import type { Schemas } from "../api/client";
import {
  isHttpSpec,
  useAction,
  useDeleteAction,
  useSaveAction,
  type Action,
  type ActionCreate,
  type ArgSpec,
  type HttpSpec,
} from "../actions";
import { TargetSelect } from "../components/TargetSelect";
import { Button, Card, ErrorMessage, SelectField, TextArea, TextField } from "../components/ui";
import { useCreateButton } from "../pads";
import { useSecrets } from "../secrets";

type SecretEnv = Schemas["SecretEnv"];
type ExecutorKind = Action["executor"];
type Method = HttpSpec["method"];

const METHODS: Method[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

const EXECUTOR_HELP: Record<ExecutorKind, string> = {
  local:
    "Runs inside the runpad container with /bin/sh. It cannot reach the host; use an SSH target for that.",
  ssh: "Runs on the SSH target with sh. Use this for anything on a host, including the one runpad runs on.",
  http: "Sends one request to the HTTP target. The target's bearer token is added automatically.",
};

export default function ActionEditorPage() {
  const { id } = useParams();
  // /actions/new?clone=<id> starts a new action from a copy of another one.
  const cloneId = useSearchParams()[0].get("clone") ?? undefined;
  const action = useAction(id);
  const source = useAction(id ? undefined : cloneId);
  if (id && !action.data) return <ErrorMessage error={action.error} />;
  if (action.data?.feature_instance_id) return <ManagedAction action={action.data} />;
  if (cloneId && !id) {
    if (!source.data) return <ErrorMessage error={source.error} />;
    return <ActionEditor key={`clone-${cloneId}`} cloneOf={source.data} />;
  }
  return <ActionEditor key={id ?? "new"} existing={action.data} />;
}

/** A copy's name: "Backup (copy)", within the 64-character limit. */
function copyName(name: string): string {
  const suffix = " (copy)";
  return name.slice(0, 64 - suffix.length) + suffix;
}

/** Feature-generated actions change only through their feature instance. */
function ManagedAction({ action }: { action: Action }) {
  const spec = action.spec;
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <h1 className="text-lg font-semibold">{action.name}</h1>
      <p className="rounded-md border border-line bg-card px-4 py-3 text-sm text-soft">
        A feature created this action, so it cannot be edited here.{" "}
        <Link to={`/features/instances/${action.feature_instance_id}`} className="underline">
          Change the feature
        </Link>{" "}
        instead. Buttons that run it can be renamed, moved or removed in the pad editor.
      </p>
      <Card title="Command">
        <dl className="grid grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted">Runs</dt>
          <dd>{action.executor}</dd>
          <dt className="text-muted">Timeout</dt>
          <dd>{action.timeout_seconds} seconds</dd>
          <dt className="text-muted">Confirmation</dt>
          <dd>{action.confirm ? "Asked before running" : "None"}</dd>
          {isHttpSpec(spec) ? (
            <>
              <dt className="text-muted">Request</dt>
              <dd className="font-mono">
                {spec.method} {spec.path}
              </dd>
            </>
          ) : (
            <>
              <dt className="text-muted">Script</dt>
              <dd>
                <pre className="overflow-x-auto rounded bg-black p-2 font-mono text-xs text-zinc-200">{spec.script}</pre>
              </dd>
              {Object.entries(spec.env ?? {}).map(([name, value]) => (
                <Fragment key={name}>
                  <dt className="font-mono text-muted">${name}</dt>
                  <dd className="font-mono">{value}</dd>
                </Fragment>
              ))}
            </>
          )}
        </dl>
      </Card>
    </div>
  );
}

const NEW_ARG: Record<ArgSpec["type"], ArgSpec> = {
  string: { type: "string", name: "", label: "", pattern: "[A-Za-z0-9._-]+", max_length: 200 },
  integer: { type: "integer", name: "", label: "", min: 0, max: 100 },
  enum: { type: "enum", name: "", label: "", choices: ["a", "b"] },
  boolean: { type: "boolean", name: "", label: "", default: false },
};

function ActionEditor({ existing, cloneOf }: { existing?: Action; cloneOf?: Action }) {
  const save = useSaveAction();
  const remove = useDeleteAction();
  const createButton = useCreateButton();
  const navigate = useNavigate();
  // Set when creating a custom button from a pad: the new action gets a button there.
  const padId = useSearchParams()[0].get("pad");

  // What the form starts from: the action being edited, or the one being cloned.
  const initial = existing ?? cloneOf;
  const existingHttp = initial && isHttpSpec(initial.spec) ? initial.spec : undefined;
  // Fixed variables have no editor here; keep any that were set through the API or by a
  // feature (when cloning one of its actions).
  const env = initial && !isHttpSpec(initial.spec) ? initial.spec.env : undefined;
  const [executor, setExecutor] = useState<ExecutorKind>(initial?.executor ?? "local");
  const [targetId, setTargetId] = useState(initial?.target_id ?? "");
  const [name, setName] = useState(cloneOf ? copyName(cloneOf.name) : (existing?.name ?? ""));
  const [description, setDescription] = useState(initial?.description ?? "");
  const [script, setScript] = useState(
    initial && !isHttpSpec(initial.spec) ? initial.spec.script : "",
  );
  const [method, setMethod] = useState<Method>(existingHttp?.method ?? "POST");
  const [path, setPath] = useState(existingHttp?.path ?? "");
  const [bodyText, setBodyText] = useState(
    existingHttp?.body ? JSON.stringify(existingHttp.body, null, 2) : "",
  );
  const [bodyError, setBodyError] = useState<Error | null>(null);
  const [args, setArgs] = useState<ArgSpec[]>(initial?.args ?? []);
  const [secretEnv, setSecretEnv] = useState<SecretEnv[]>(initial?.secret_env ?? []);
  const [timeout, setTimeoutSeconds] = useState(String(initial?.timeout_seconds ?? 30));
  const [concurrency, setConcurrency] = useState(initial?.concurrency ?? "reject");
  const [confirm, setConfirm] = useState(initial?.confirm ?? false);

  function parseBody(): HttpSpec["body"] | undefined {
    if (!bodyText.trim()) return null;
    try {
      return JSON.parse(bodyText) as HttpSpec["body"];
    } catch {
      setBodyError(new Error("Body is not valid JSON"));
      return undefined;
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setBodyError(null);
    const common = {
      name,
      description,
      args,
      timeout_seconds: Number(timeout),
      concurrency,
      confirm,
    };
    let body: ActionCreate;
    if (executor === "http") {
      const parsed = parseBody();
      if (parsed === undefined) return;
      body = {
        ...common,
        executor,
        target_id: targetId,
        spec: { method, path, body: parsed },
        secret_env: [],
      };
    } else if (executor === "ssh") {
      body = { ...common, executor, target_id: targetId, spec: { script, env }, secret_env: secretEnv };
    } else {
      body = { ...common, executor, spec: { script, env }, secret_env: secretEnv };
    }
    save.mutate(
      { id: existing?.id, body },
      {
        onSuccess: (action) => {
          if (padId && !existing) {
            createButton.mutate(
              { padId, action_id: action.id, label: action.name },
              { onSuccess: () => void navigate(`/pads/${padId}`) },
            );
          } else {
            void navigate(padId ? `/pads/${padId}` : "/actions");
          }
        },
      },
    );
  }

  function confirmDelete() {
    if (!existing) return;
    if (window.confirm(`Delete action "${existing.name}"? Its run history is kept.`)) {
      remove.mutate(existing.id, { onSuccess: () => void navigate("/actions") });
    }
  }

  return (
    <form onSubmit={submit} className="flex max-w-3xl flex-col gap-6">
      <h1 className="text-lg font-semibold">
        {existing
          ? `Edit ${existing.name}`
          : cloneOf
            ? `Clone ${cloneOf.name}`
            : padId
              ? "New custom button"
              : "New action"}
      </h1>
      <Card title="Command">
        <div className="flex flex-col gap-4">
          <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <SelectField
            label="Runs"
            value={executor}
            onChange={(e) => {
              const next = e.target.value as ExecutorKind;
              setExecutor(next);
              // Switching back restores the starting target; any other change needs a new one.
              setTargetId(next === initial?.executor ? (initial.target_id ?? "") : "");
            }}
            hint={
              existing && executor !== existing.executor
                ? `${EXECUTOR_HELP[executor]} Buttons and run history stay with this action.`
                : EXECUTOR_HELP[executor]
            }
          >
            <option value="local">In the runpad container (local)</option>
            <option value="ssh">On an SSH host</option>
            <option value="http">As an HTTP request</option>
          </SelectField>
          {executor !== "local" && (
            <TargetSelect kind={executor} value={targetId} onChange={setTargetId} />
          )}
          {executor === "http" ? (
            <>
              <div className="grid grid-cols-[8rem_1fr] gap-3">
                <SelectField
                  label="Method"
                  value={method}
                  onChange={(e) => setMethod(e.target.value as Method)}
                >
                  {METHODS.map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </SelectField>
                <TextField
                  label="Path"
                  placeholder="services/{domain}/turn_on"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  hint="Relative to the target's base URL. {name} is replaced with the argument, URL-encoded."
                />
              </div>
              <TextArea
                label="JSON body (optional)"
                rows={6}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                hint='A string that is exactly "{name}" becomes the typed value; inside longer strings it is replaced with the text.'
              />
              <ErrorMessage error={bodyError} />
            </>
          ) : (
            <TextArea
              label="Script"
              required
              rows={8}
              value={script}
              onChange={(e) => setScript(e.target.value)}
              hint='Arguments arrive as "$ARG_NAME" and as "$1", "$2", ... in the order below. Quote them. They are never pasted into the script text.'
            />
          )}
        </div>
      </Card>

      <Card title="Arguments">
        <ArgsEditor args={args} http={executor === "http"} onChange={setArgs} />
      </Card>

      {executor !== "http" && (
        <Card title="Secret variables">
          <SecretEnvEditor items={secretEnv} onChange={setSecretEnv} />
        </Card>
      )}

      <Card title="Behavior">
        <div className="flex flex-col gap-4">
          <TextField
            label="Timeout (seconds)"
            type="number"
            min={1}
            max={3600}
            required
            value={timeout}
            onChange={(e) => setTimeoutSeconds(e.target.value)}
          />
          <SelectField
            label="While a run is in progress"
            value={concurrency}
            onChange={(e) => setConcurrency(e.target.value as Action["concurrency"])}
          >
            <option value="reject">Refuse to start another run</option>
            <option value="allow">Allow runs to overlap</option>
          </SelectField>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            Ask for confirmation before running (use for destructive actions)
          </label>
        </div>
      </Card>

      <ErrorMessage error={save.error ?? remove.error ?? createButton.error} />
      <div className="flex justify-between">
        <Button type="submit" disabled={save.isPending}>
          {existing ? "Save" : padId ? "Create button" : "Create action"}
        </Button>
        {existing && (
          <Button
            type="button"
            variant="danger"
            onClick={confirmDelete}
            tooltip="Delete the action and every button for it. Its run history is kept."
          >
            Delete
          </Button>
        )}
      </div>
    </form>
  );
}

/** An argument name from what was typed: "$ARG_RUN_HOST", "RUN_HOST", "{run_host}", and
 * "run host" all become run_host. */
function argName(typed: string): string {
  return typed
    .toLowerCase()
    .replace(/[{}$]/g, "")
    .replace(/^arg_/, "")
    .replace(/[^a-z0-9_]/g, "_");
}

function ArgsEditor({
  args,
  http,
  onChange,
}: {
  args: ArgSpec[];
  http: boolean;
  onChange: (args: ArgSpec[]) => void;
}) {
  const [newType, setNewType] = useState<ArgSpec["type"]>("string");

  function update(index: number, arg: ArgSpec) {
    onChange(args.map((current, i) => (i === index ? arg : current)));
  }

  return (
    <div className="flex flex-col gap-4">
      {args.length === 0 && (
        <p className="text-sm text-faint">No arguments. The button runs as-is.</p>
      )}
      {args.map((arg, index) => (
        <div key={index} className="flex flex-col gap-3 rounded-md border border-line p-3">
          {/* Top-aligned: the name's hint would push the other fields out of line. */}
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <TextField
                label="Name"
                required
                placeholder={http ? "host" : "HOST"}
                maxLength={32}
                pattern={http ? "[a-z][a-z0-9_]*" : "[A-Z][A-Z0-9_]*"}
                title="Starts with a letter; letters, digits and underscores"
                hint={
                  http
                    ? `Used as {${arg.name || "name"}} in the path and body.`
                    : `The script gets it as $ARG_${arg.name.toUpperCase() || "NAME"} and $${index + 1}.`
                }
                value={http ? arg.name : arg.name.toUpperCase()}
                onChange={(e) => update(index, { ...arg, name: argName(e.target.value) })}
              />
            </div>
            <div className="flex-1">
              <TextField
                label="Label"
                value={arg.label ?? ""}
                onChange={(e) => update(index, { ...arg, label: e.target.value })}
              />
            </div>
            <Button
              type="button"
              variant="secondary"
              className="mt-6"
              onClick={() => onChange(args.filter((_, i) => i !== index))}
              tooltip="Remove this argument. Later arguments move up one position ($2 becomes $1)."
            >
              Remove
            </Button>
          </div>
          <ArgTypeFields arg={arg} onChange={(next) => update(index, next)} />
        </div>
      ))}
      <div className="flex items-end gap-2">
        <SelectField
          label="Add argument"
          value={newType}
          onChange={(e) => setNewType(e.target.value as ArgSpec["type"])}
        >
          <option value="string">Text (must match a pattern)</option>
          <option value="integer">Whole number (within a range)</option>
          <option value="enum">Choice from a list</option>
          <option value="boolean">Yes / no</option>
        </SelectField>
        <Button
          type="button"
          variant="secondary"
          onClick={() => onChange([...args, NEW_ARG[newType]])}
          tooltip="Add an argument of the chosen type. Whoever presses the button fills it in."
        >
          Add
        </Button>
      </div>
    </div>
  );
}

function ArgTypeFields({ arg, onChange }: { arg: ArgSpec; onChange: (arg: ArgSpec) => void }) {
  switch (arg.type) {
    case "string":
      return (
        <div className="grid grid-cols-3 gap-3">
          <TextField
            label="Pattern (whole value must match)"
            required
            value={arg.pattern}
            onChange={(e) => onChange({ ...arg, pattern: e.target.value })}
          />
          <TextField
            label="Max length"
            type="number"
            min={1}
            max={1000}
            value={String(arg.max_length ?? 200)}
            onChange={(e) => onChange({ ...arg, max_length: Number(e.target.value) })}
          />
          <TextField
            label="Default (empty = required)"
            value={arg.default ?? ""}
            onChange={(e) => onChange({ ...arg, default: e.target.value || null })}
          />
        </div>
      );
    case "integer":
      return (
        <div className="grid grid-cols-3 gap-3">
          <TextField
            label="Min"
            type="number"
            required
            value={String(arg.min)}
            onChange={(e) => onChange({ ...arg, min: Number(e.target.value) })}
          />
          <TextField
            label="Max"
            type="number"
            required
            value={String(arg.max)}
            onChange={(e) => onChange({ ...arg, max: Number(e.target.value) })}
          />
          <TextField
            label="Default (empty = required)"
            type="number"
            value={arg.default === null || arg.default === undefined ? "" : String(arg.default)}
            onChange={(e) =>
              onChange({ ...arg, default: e.target.value === "" ? null : Number(e.target.value) })
            }
          />
        </div>
      );
    case "enum":
      return (
        <div className="grid grid-cols-2 gap-3">
          <TextField
            label="Choices (comma separated)"
            required
            value={arg.choices.join(",")}
            onChange={(e) =>
              onChange({ ...arg, choices: e.target.value.split(",").map((c) => c.trim()) })
            }
          />
          <TextField
            label="Default (empty = required)"
            value={arg.default ?? ""}
            onChange={(e) => onChange({ ...arg, default: e.target.value || null })}
          />
        </div>
      );
    case "boolean":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={arg.default ?? false}
            onChange={(e) => onChange({ ...arg, default: e.target.checked })}
          />
          On by default (passed as "true" or "false")
        </label>
      );
  }
}

function SecretEnvEditor({
  items,
  onChange,
}: {
  items: SecretEnv[];
  onChange: (items: SecretEnv[]) => void;
}) {
  const secrets = useSecrets();
  const textSecrets = secrets.data?.filter((s) => s.kind === "text") ?? [];

  function update(index: number, item: SecretEnv) {
    onChange(items.map((current, i) => (i === index ? item : current)));
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">
        Expose text secrets to the script as environment variables. Their values are replaced
        with [redacted] in run output.
      </p>
      {items.map((item, index) => (
        <div key={index} className="flex items-end gap-3">
          <div className="flex-1">
            <TextField
              label="Variable"
              required
              pattern="[A-Z][A-Z0-9_]{0,63}"
              title="Upper-case letters, digits and underscores"
              placeholder="API_TOKEN"
              value={item.name}
              onChange={(e) => update(index, { ...item, name: e.target.value.toUpperCase() })}
            />
          </div>
          <div className="flex-1">
            <SelectField
              label="Secret"
              required
              value={item.secret_id}
              onChange={(e) => update(index, { ...item, secret_id: e.target.value })}
            >
              <option value="" disabled>
                Choose a secret
              </option>
              {textSecrets.map((secret) => (
                <option key={secret.id} value={secret.id}>
                  {secret.name}
                </option>
              ))}
            </SelectField>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => onChange(items.filter((_, i) => i !== index))}
            tooltip="Stop exposing this secret to the script."
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        className="self-start"
        onClick={() => onChange([...items, { name: "", secret_id: "" }])}
        tooltip="Expose a text secret to the script as an environment variable."
      >
        Add secret variable
      </Button>
    </div>
  );
}
