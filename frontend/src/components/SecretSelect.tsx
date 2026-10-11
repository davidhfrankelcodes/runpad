import { Link } from "react-router";
import { useSecrets } from "../secrets";
import { SelectField } from "./ui";

/** Picks a text Secret (a password or API token), with a link to add one when there are
 * none. The value never reaches the browser; only the secret's name and id do. */
export function SecretSelect({
  value,
  onChange,
  label = "Secret",
  hint,
}: {
  value: string;
  onChange: (id: string) => void;
  label?: string;
  hint?: string;
}) {
  const secrets = useSecrets();
  const matching = secrets.data?.filter((s) => s.kind === "text") ?? [];
  return (
    <SelectField
      label={label}
      required
      value={value}
      onChange={(e) => onChange(e.target.value)}
      hint={
        matching.length === 0 ? (
          <>
            No text secrets yet. <Link to="/secrets" className="underline">Add one</Link> first,
            holding the token.
          </>
        ) : (
          hint
        )
      }
    >
      <option value="" disabled>
        Choose a secret
      </option>
      {matching.map((secret) => (
        <option key={secret.id} value={secret.id}>
          {secret.name}
        </option>
      ))}
    </SelectField>
  );
}
