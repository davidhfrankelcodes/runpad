import { Link } from "react-router";
import { useTargets } from "../targets";
import { SelectField } from "./ui";

/** Picks a Target of one kind, with a link to add one when there are none. */
export function TargetSelect({
  kind,
  value,
  onChange,
  label = "Target",
  hint,
}: {
  kind: "ssh" | "http";
  value: string;
  onChange: (id: string) => void;
  label?: string;
  hint?: string;
}) {
  const targets = useTargets();
  const matching = targets.data?.filter((t) => t.kind === kind) ?? [];
  return (
    <SelectField
      label={label}
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
      hint={
        matching.length === 0 ? (
          <>
            No {kind} targets yet. <Link to="/targets" className="underline">Add one</Link>{" "}
            first.
          </>
        ) : (
          hint
        )
      }
    >
      <option value="" disabled>
        Choose a target
      </option>
      {matching.map((target) => (
        <option key={target.id} value={target.id}>
          {target.name}
        </option>
      ))}
    </SelectField>
  );
}
