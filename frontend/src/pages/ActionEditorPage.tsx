import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";
import type { Schemas } from "../api/client";
import { useAction, useDeleteAction, useSaveAction, type Action, type ArgSpec } from "../actions";
import { Button, Card, ErrorMessage, SelectField, TextArea, TextField } from "../components/ui";
import { useSecrets } from "../secrets";

type SecretEnv = Schemas["SecretEnv"];

export default function ActionEditorPage() {
  const { id } = useParams();
  const action = useAction(id);
  if (id && !action.data) return <ErrorMessage error={action.error} />;
  return <ActionEditor key={id ?? "new"} existing={action.data} />;
}

const NEW_ARG: Record<ArgSpec["type"], ArgSpec> = {
  string: { type: "string", name: "", label: "", pattern: "[A-Za-z0-9._-]+", max_length: 200 },
  integer: { type: "integer", name: "", label: "", min: 0, max: 100 },
  enum: { type: "enum", name: "", label: "", choices: ["a", "b"] },
  boolean: { type: "boolean", name: "", label: "", default: false },
};

function ActionEditor({ existing }: { existing?: Action }) {
  const save = useSaveAction();
  const remove = useDeleteAction();
  const navigate = useNavigate();

  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [script, setScript] = useState(existing?.spec.script ?? "");
  const [args, setArgs] = useState<ArgSpec[]>(existing?.args ?? []);
  const [secretEnv, setSecretEnv] = useState<SecretEnv[]>(existing?.secret_env ?? []);
  const [timeout, setTimeoutSeconds] = useState(String(existing?.timeout_seconds ?? 30));
  const [concurrency, setConcurrency] = useState(existing?.concurrency ?? "reject");
  const [confirm, setConfirm] = useState(existing?.confirm ?? false);

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      {
        id: existing?.id,
        body: {
          name,
          description,
          executor: "local",
          spec: { script },
          args,
          secret_env: secretEnv,
          timeout_seconds: Number(timeout),
          concurrency,
          confirm,
        },
      },
      { onSuccess: () => void navigate("/actions") },
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
      <h1 className="text-lg font-semibold">{existing ? `Edit ${existing.name}` : "New action"}</h1>
      <Card title="Command">
        <div className="flex flex-col gap-4">
          <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <p className="text-sm text-zinc-400">
            Runs inside the runpad container with <code>/bin/sh -c</code>. It cannot reach the
            host; use an SSH target for that.
          </p>
          <TextArea
            label="Script"
            required
            rows={8}
            value={script}
            onChange={(e) => setScript(e.target.value)}
            hint='Arguments arrive as "$ARG_NAME" and as "$1", "$2", ... in the order below. Quote them. They are never pasted into the script text.'
          />
        </div>
      </Card>

      <Card title="Arguments">
        <ArgsEditor args={args} onChange={setArgs} />
      </Card>

      <Card title="Secret variables">
        <SecretEnvEditor items={secretEnv} onChange={setSecretEnv} />
      </Card>

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

      <ErrorMessage error={save.error ?? remove.error} />
      <div className="flex justify-between">
        <Button type="submit" disabled={save.isPending}>
          {existing ? "Save" : "Create action"}
        </Button>
        {existing && (
          <Button type="button" variant="danger" onClick={confirmDelete}>
            Delete
          </Button>
        )}
      </div>
    </form>
  );
}

function ArgsEditor({ args, onChange }: { args: ArgSpec[]; onChange: (args: ArgSpec[]) => void }) {
  const [newType, setNewType] = useState<ArgSpec["type"]>("string");

  function update(index: number, arg: ArgSpec) {
    onChange(args.map((current, i) => (i === index ? arg : current)));
  }

  return (
    <div className="flex flex-col gap-4">
      {args.length === 0 && (
        <p className="text-sm text-zinc-500">No arguments. The button runs as-is.</p>
      )}
      {args.map((arg, index) => (
        <div key={index} className="flex flex-col gap-3 rounded-md border border-zinc-800 p-3">
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <TextField
                label={`Name ($ARG_${arg.name.toUpperCase() || "NAME"}, $${index + 1})`}
                required
                pattern="[a-z][a-z0-9_]{0,31}"
                title="Lowercase letters, digits and underscores, starting with a letter"
                value={arg.name}
                onChange={(e) => update(index, { ...arg, name: e.target.value })}
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
              onClick={() => onChange(args.filter((_, i) => i !== index))}
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
        <Button type="button" variant="secondary" onClick={() => onChange([...args, NEW_ARG[newType]])}>
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
      <p className="text-sm text-zinc-400">
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
      >
        Add secret variable
      </Button>
    </div>
  );
}
