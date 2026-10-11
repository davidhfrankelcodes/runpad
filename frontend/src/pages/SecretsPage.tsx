import { useState, type FormEvent } from "react";
import type { Schemas } from "../api/client";
import {
  Badge,
  Button,
  Card,
  CopyableText,
  ErrorMessage,
  SelectField,
  TextArea,
  TextField,
} from "../components/ui";
import {
  useCreateSecret,
  useDeleteSecret,
  useGenerateSshKey,
  useSecrets,
  useUpdateSecret,
} from "../secrets";

type Secret = Schemas["SecretRead"];

export default function SecretsPage() {
  const secrets = useSecrets();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Secrets</h1>
        <p className="text-sm text-zinc-400">
          Encrypted at rest. Values are write-only: once saved they are never shown again.
        </p>
      </div>
      <ErrorMessage error={secrets.error} />
      {secrets.data?.length === 0 && <p className="text-sm text-zinc-500">No secrets yet.</p>}
      <div className="flex flex-col gap-3">
        {secrets.data?.map((secret) => <SecretCard key={secret.id} secret={secret} />)}
      </div>
      <AddSecretForm />
    </div>
  );
}

function SecretCard({ secret }: { secret: Secret }) {
  const update = useUpdateSecret();
  const remove = useDeleteSecret();
  const [replacing, setReplacing] = useState(false);
  const [value, setValue] = useState("");

  function replace(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      { id: secret.id, value },
      {
        onSuccess: () => {
          setReplacing(false);
          setValue("");
        },
      },
    );
  }

  function confirmDelete() {
    if (window.confirm(`Delete secret "${secret.name}"? This cannot be undone.`)) {
      remove.mutate(secret.id);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-zinc-800 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{secret.name}</span>
            <Badge>{secret.kind}</Badge>
          </div>
          {secret.description && <p className="text-sm text-zinc-400">{secret.description}</p>}
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setReplacing(!replacing)}>
            Replace value
          </Button>
          <Button variant="danger" disabled={remove.isPending} onClick={confirmDelete}>
            Delete
          </Button>
        </div>
      </div>
      {secret.public_key && (
        <CopyableText label="Public key (add to authorized_keys)" value={secret.public_key} />
      )}
      {replacing && (
        <form onSubmit={replace} className="flex flex-col gap-3">
          {secret.kind === "ssh_key" ? (
            <TextArea
              label="New private key"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          ) : (
            <TextField
              label="New value"
              type="password"
              autoComplete="off"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          )}
          <Button type="submit" disabled={update.isPending} className="self-start">
            Save
          </Button>
        </form>
      )}
      <ErrorMessage error={update.error ?? remove.error} />
    </div>
  );
}

type Mode = "generate" | "import" | "text";

function AddSecretForm() {
  const generate = useGenerateSshKey();
  const create = useCreateSecret();
  const [mode, setMode] = useState<Mode>("generate");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [value, setValue] = useState("");
  const [created, setCreated] = useState<Secret | null>(null);
  const pending = generate.isPending || create.isPending;

  function submit(event: FormEvent) {
    event.preventDefault();
    const onSuccess = (secret: Secret) => {
      setCreated(secret);
      setName("");
      setDescription("");
      setValue("");
    };
    if (mode === "generate") {
      generate.mutate({ name, description }, { onSuccess });
    } else {
      const kind = mode === "import" ? "ssh_key" : "text";
      create.mutate({ name, description, kind, value }, { onSuccess });
    }
  }

  return (
    <Card title="Add secret">
      <form onSubmit={submit} className="flex max-w-xl flex-col gap-4">
        <SelectField
          label="Type"
          value={mode}
          onChange={(e) => {
            setMode(e.target.value as Mode);
            setCreated(null);
          }}
        >
          <option value="generate">Generate a new SSH key (recommended)</option>
          <option value="import">Import an existing SSH private key</option>
          <option value="text">Text: a token or password</option>
        </SelectField>
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        {mode === "import" && (
          <TextArea
            label="Private key"
            hint="OpenSSH or PEM format, without a passphrase."
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        {mode === "text" && (
          <TextField
            label="Value"
            type="password"
            autoComplete="off"
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        <ErrorMessage error={generate.error ?? create.error} />
        <Button type="submit" disabled={pending}>
          {mode === "generate" ? "Generate key" : "Save secret"}
        </Button>
        {created?.public_key && (
          <div className="flex flex-col gap-2 rounded-md bg-emerald-950/40 p-3 text-sm">
            <p>
              Saved <strong>{created.name}</strong>. Add this public key to{" "}
              <code>~/.ssh/authorized_keys</code> for the user runpad will log in as:
            </p>
            <CopyableText value={created.public_key} />
          </div>
        )}
      </form>
    </Card>
  );
}
