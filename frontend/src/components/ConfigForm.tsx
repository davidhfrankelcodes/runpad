import { useId } from "react";
import type { ConfigField, ConfigValue, ConfigValues } from "../features";
import { TargetSelect } from "./TargetSelect";
import { SelectField, TextArea, TextField } from "./ui";

/** A feature's setup form, rendered from its config schema. The server validates every
 * value again; patterns are not copied to the inputs because browsers parse them with
 * different regular expression rules than Python. */
export function ConfigForm({
  fields,
  values,
  onChange,
}: {
  fields: ConfigField[];
  values: ConfigValues;
  onChange: (values: ConfigValues) => void;
}) {
  function set(name: string, value: ConfigValue) {
    onChange({ ...values, [name]: value });
  }

  return (
    <div className="flex flex-col gap-4">
      {fields.map((field) => (
        <ConfigInput
          key={field.name}
          field={field}
          value={values[field.name]}
          onChange={(value) => set(field.name, value)}
        />
      ))}
    </div>
  );
}

function ConfigInput({
  field,
  value,
  onChange,
}: {
  field: ConfigField;
  value: ConfigValue | undefined;
  onChange: (value: ConfigValue) => void;
}) {
  if (field.targetKind) {
    return (
      <TargetSelect
        kind={field.targetKind}
        label={field.title}
        hint={field.description}
        value={typeof value === "string" ? value : ""}
        onChange={onChange}
      />
    );
  }
  if (field.choices) {
    return (
      <SelectField
        label={field.title}
        hint={field.description}
        required={field.required}
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>
          Choose
        </option>
        {field.choices.map((choice) => (
          <option key={choice}>{choice}</option>
        ))}
      </SelectField>
    );
  }
  if (field.type === "boolean") {
    return <CheckboxField field={field} checked={value === true} onChange={onChange} />;
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <TextField
        label={field.title}
        hint={field.description}
        type="number"
        required={field.required}
        min={field.minimum}
        max={field.maximum}
        step={field.type === "integer" ? 1 : "any"}
        value={typeof value === "number" ? String(value) : ""}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }
  if (field.multiline) {
    return (
      <TextArea
        label={field.title}
        hint={field.description}
        required={field.required}
        maxLength={field.maxLength}
        rows={5}
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <TextField
      label={field.title}
      hint={field.description}
      required={field.required}
      maxLength={field.maxLength}
      value={typeof value === "string" ? value : ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function CheckboxField({
  field,
  checked,
  onChange,
}: {
  field: ConfigField;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const hintId = useId();
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked}
          aria-describedby={field.description ? hintId : undefined}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.title}
      </label>
      {field.description && (
        <span id={hintId} className="text-xs text-zinc-500">
          {field.description}
        </span>
      )}
    </div>
  );
}
