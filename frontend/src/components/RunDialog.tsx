import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useRunAction, type Action, type ArgSpec, type ArgValue } from "../actions";
import { Button, ErrorMessage, SelectField, TextField } from "./ui";

function initialValue(arg: ArgSpec): ArgValue | "" {
  return arg.default ?? (arg.type === "boolean" ? false : "");
}

/** Collects arguments and confirmation, starts the Run, and opens its output page. */
export function RunDialog({ action, onClose }: { action: Action; onClose: () => void }) {
  const run = useRunAction();
  const navigate = useNavigate();
  const [values, setValues] = useState<Record<string, ArgValue | "">>(() =>
    Object.fromEntries(action.args.map((arg) => [arg.name, initialValue(arg)])),
  );

  function set(name: string, value: ArgValue | "") {
    setValues((current) => ({ ...current, [name]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const args = Object.fromEntries(
      Object.entries(values).filter((entry): entry is [string, ArgValue] => entry[1] !== ""),
    );
    run.mutate(
      { id: action.id, args },
      { onSuccess: (started) => void navigate(`/runs/${started.id}`) },
    );
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="flex w-full max-w-md flex-col gap-4 rounded-lg border border-zinc-700 bg-zinc-900 p-5"
      >
        <div>
          <h2 className="text-base font-semibold">Run {action.name}</h2>
          {action.description && <p className="text-sm text-zinc-400">{action.description}</p>}
        </div>
        {action.args.map((arg) => (
          <ArgInput key={arg.name} arg={arg} value={values[arg.name] ?? ""} onChange={set} />
        ))}
        {action.confirm && (
          <p className="rounded-md bg-amber-950 px-3 py-2 text-sm text-amber-200">
            This action is marked as requiring confirmation. Are you sure?
          </p>
        )}
        <ErrorMessage error={run.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant={action.confirm ? "danger" : "primary"} disabled={run.isPending}>
            {action.confirm ? "Yes, run it" : "Run"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function ArgInput({
  arg,
  value,
  onChange,
}: {
  arg: ArgSpec;
  value: ArgValue | "";
  onChange: (name: string, value: ArgValue | "") => void;
}) {
  const label = arg.label || arg.name;
  const required = arg.default === null || arg.default === undefined;
  switch (arg.type) {
    case "boolean":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value === true}
            onChange={(e) => onChange(arg.name, e.target.checked)}
          />
          {label}
        </label>
      );
    case "enum":
      return (
        <SelectField
          label={label}
          required={required}
          value={String(value)}
          onChange={(e) => onChange(arg.name, e.target.value)}
        >
          {required && <option value="">Choose...</option>}
          {arg.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </SelectField>
      );
    case "integer":
      return (
        <TextField
          label={label}
          type="number"
          required={required}
          min={arg.min}
          max={arg.max}
          hint={`${arg.min} to ${arg.max}`}
          value={String(value)}
          onChange={(e) => onChange(arg.name, e.target.value === "" ? "" : Number(e.target.value))}
        />
      );
    case "string":
      return (
        <TextField
          label={label}
          required={required}
          maxLength={arg.max_length}
          hint={`Must match ${arg.pattern}`}
          value={String(value)}
          onChange={(e) => onChange(arg.name, e.target.value)}
        />
      );
  }
}
