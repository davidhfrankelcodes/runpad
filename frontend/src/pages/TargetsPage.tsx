import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Badge, Button, Card, ErrorMessage, SelectField, TextField } from "../components/ui";
import { useSecrets } from "../secrets";
import {
  isSshConfig,
  useCreateTarget,
  useDeleteTarget,
  useScanHostKey,
  useTargets,
  useTestTarget,
  useUpdateTarget,
  type HostKey,
  type Target,
} from "../targets";

export default function TargetsPage() {
  const targets = useTargets();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Targets</h1>
        <p className="text-sm text-muted">
          Where actions run: SSH hosts (including the machine runpad runs on) and HTTP endpoints.
        </p>
      </div>
      <ErrorMessage error={targets.error} />
      {targets.data?.length === 0 && <p className="text-sm text-faint">No targets yet.</p>}
      <div className="flex flex-col gap-3">
        {targets.data?.map((target) => <TargetCard key={target.id} target={target} />)}
      </div>
      <Card title="Add target">
        <TargetForm />
      </Card>
    </div>
  );
}

function TargetCard({ target }: { target: Target }) {
  const test = useTestTarget();
  const remove = useDeleteTarget();
  const [editing, setEditing] = useState(false);
  const config = target.config;

  function confirmDelete() {
    if (window.confirm(`Delete target "${target.name}"?`)) remove.mutate(target.id);
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{target.name}</span>
            <Badge
              tooltip={
                target.kind === "ssh"
                  ? "An SSH host. Its host key is pinned: if it changes, runs fail."
                  : "An HTTP endpoint. Its bearer token, if any, is sent with every request."
              }
            >
              {target.kind}
            </Badge>
          </div>
          {isSshConfig(config) ? (
            <>
              <span className="font-mono text-sm text-soft">
                {config.username}@{config.host}:{config.port}
              </span>
              <span className="font-mono text-xs text-faint">
                host key {config.host_key_fingerprint}
              </span>
            </>
          ) : (
            <span className="font-mono text-sm text-soft">
              {config.base_url}
              {!config.verify_tls && <span className="ml-2 text-amber-400">(TLS not verified)</span>}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            disabled={test.isPending}
            onClick={() => test.mutate(target.id)}
            tooltip={
              target.kind === "ssh"
                ? "Connect and log in, without running anything."
                : "Send a GET to the base URL, and check it answers and accepts the token."
            }
          >
            {test.isPending ? "Testing..." : "Test"}
          </Button>
          <Button variant="secondary" onClick={() => setEditing(!editing)}>
            Edit
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={confirmDelete}
            tooltip="Only possible when no action uses this target."
          >
            Delete
          </Button>
        </div>
      </div>
      {test.data && (
        <p className={`text-sm ${test.data.ok ? "text-emerald-400" : "text-red-400"}`}>
          {test.data.message}
        </p>
      )}
      <ErrorMessage error={test.error ?? remove.error} />
      {editing && (
        <div className="border-t border-line pt-4">
          <TargetForm existing={target} onDone={() => setEditing(false)} />
        </div>
      )}
    </div>
  );
}

function TargetForm({ existing, onDone }: { existing?: Target; onDone?: () => void }) {
  const [kind, setKind] = useState<Target["kind"]>(existing?.kind ?? "ssh");

  return (
    <div className="flex max-w-xl flex-col gap-4">
      {!existing && (
        <SelectField
          label="Type"
          value={kind}
          onChange={(e) => setKind(e.target.value as Target["kind"])}
        >
          <option value="ssh">SSH host</option>
          <option value="http">HTTP endpoint</option>
        </SelectField>
      )}
      {kind === "ssh" ? (
        <SshTargetForm existing={existing} onDone={onDone} />
      ) : (
        <HttpTargetForm existing={existing} onDone={onDone} />
      )}
    </div>
  );
}

function SshTargetForm({ existing, onDone }: { existing?: Target; onDone?: () => void }) {
  const secrets = useSecrets();
  const create = useCreateTarget();
  const update = useUpdateTarget();
  const scan = useScanHostKey();
  const initial = existing && isSshConfig(existing.config) ? existing.config : undefined;

  const [name, setName] = useState(existing?.name ?? "");
  const [host, setHost] = useState(initial?.host ?? "");
  const [port, setPort] = useState(String(initial?.port ?? 22));
  const [username, setUsername] = useState(initial?.username ?? "");
  const [secretId, setSecretId] = useState(existing?.secret_id ?? "");
  const [scanned, setScanned] = useState<HostKey | null>(null);
  const [verified, setVerified] = useState(false);

  const keys = secrets.data?.filter((s) => s.kind === "ssh_key") ?? [];
  const endpointChanged = !initial || initial.host !== host || String(initial.port) !== port;
  // A new host key is required for new targets and whenever host or port change.
  const hostKey = scanned?.public_key ?? (endpointChanged ? null : initial?.host_key);
  const ready = hostKey !== null && hostKey !== undefined && (!scanned || verified);
  const mutation = existing ? update : create;

  function scanHost() {
    setVerified(false);
    scan.mutate({ host, port: Number(port) }, { onSuccess: setScanned });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!hostKey) return;
    const config = { host, port: Number(port), username, host_key: hostKey };
    const reset = () => {
      setScanned(null);
      setVerified(false);
      onDone?.();
    };
    if (existing) {
      update.mutate({ id: existing.id, name, secret_id: secretId, config }, { onSuccess: reset });
    } else {
      create.mutate(
        { kind: "ssh", name, secret_id: secretId, config },
        {
          onSuccess: () => {
            setName("");
            setHost("");
            setPort("22");
            setUsername("");
            reset();
          },
        },
      );
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      <div className="grid grid-cols-[1fr_6rem] gap-3">
        <TextField
          label="Host"
          required
          placeholder="nas.lan or 192.168.1.10"
          value={host}
          onChange={(e) => {
            setHost(e.target.value);
            setScanned(null);
          }}
        />
        <TextField
          label="Port"
          type="number"
          min={1}
          max={65535}
          required
          value={port}
          onChange={(e) => {
            setPort(e.target.value);
            setScanned(null);
          }}
        />
      </div>
      <TextField
        label="Username"
        required
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <SelectField
        label="SSH key"
        required
        value={secretId}
        onChange={(e) => setSecretId(e.target.value)}
        hint={
          keys.length === 0 ? (
            <>
              No SSH keys yet. <Link to="/secrets" className="underline">Generate one</Link> first.
            </>
          ) : undefined
        }
      >
        <option value="" disabled>
          Choose a key
        </option>
        {keys.map((key) => (
          <option key={key.id} value={key.id}>
            {key.name}
          </option>
        ))}
      </SelectField>

      <div className="flex flex-col gap-2 rounded-md border border-line p-3 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="text-soft">Host key</span>
          <Button
            type="button"
            variant="secondary"
            disabled={!host || scan.isPending}
            onClick={scanHost}
            tooltip="Fetch the key the host presents now, so you can compare its fingerprint before pinning it."
          >
            {scan.isPending ? "Scanning..." : existing ? "Re-scan host key" : "Scan host key"}
          </Button>
        </div>
        {!scanned && initial && !endpointChanged && (
          <p className="font-mono text-xs text-muted">Pinned: {initial.host_key_fingerprint}</p>
        )}
        {!scanned && endpointChanged && (
          <p className="text-xs text-faint">
            Scan the host to read its key. runpad pins it and refuses to connect if it changes.
          </p>
        )}
        {scanned && (
          <>
            <p className="font-mono text-xs">
              {scanned.algorithm} {scanned.fingerprint}
            </p>
            <p className="text-xs text-faint">
              Compare with the output of <code>ssh-keygen -lf /etc/ssh/ssh_host_*_key.pub</code> on
              the host.
            </p>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={verified}
                onChange={(e) => setVerified(e.target.checked)}
              />
              I have checked this fingerprint and trust it
            </label>
          </>
        )}
        <ErrorMessage error={scan.error} />
      </div>

      <ErrorMessage error={mutation.error} />
      <Button type="submit" disabled={!ready || mutation.isPending}>
        {existing ? "Save" : "Add SSH target"}
      </Button>
    </form>
  );
}

function HttpTargetForm({ existing, onDone }: { existing?: Target; onDone?: () => void }) {
  const secrets = useSecrets();
  const create = useCreateTarget();
  const update = useUpdateTarget();
  const initial = existing && !isSshConfig(existing.config) ? existing.config : undefined;

  const [name, setName] = useState(existing?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [verifyTls, setVerifyTls] = useState(initial?.verify_tls ?? true);
  const [secretId, setSecretId] = useState(existing?.secret_id ?? "");

  const tokens = secrets.data?.filter((s) => s.kind === "text") ?? [];
  const mutation = existing ? update : create;

  function submit(event: FormEvent) {
    event.preventDefault();
    const config = { base_url: baseUrl, verify_tls: verifyTls };
    if (existing) {
      update.mutate(
        {
          id: existing.id,
          name,
          config,
          ...(secretId ? { secret_id: secretId } : { clear_secret: true }),
        },
        { onSuccess: () => onDone?.() },
      );
    } else {
      create.mutate(
        { kind: "http", name, config, secret_id: secretId || null },
        {
          onSuccess: () => {
            setName("");
            setBaseUrl("");
            setVerifyTls(true);
            setSecretId("");
          },
        },
      );
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      <TextField
        label="Base URL"
        type="url"
        required
        placeholder="http://homeassistant.lan:8123/api/"
        value={baseUrl}
        onChange={(e) => setBaseUrl(e.target.value)}
      />
      <SelectField
        label="Bearer token"
        value={secretId}
        onChange={(e) => setSecretId(e.target.value)}
        hint="Sent as an Authorization header. Create text secrets on the Secrets page."
      >
        <option value="">None</option>
        {tokens.map((token) => (
          <option key={token.id} value={token.id}>
            {token.name}
          </option>
        ))}
      </SelectField>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={verifyTls}
          onChange={(e) => setVerifyTls(e.target.checked)}
        />
        Verify TLS certificate (turn off only for self-signed certificates)
      </label>
      <ErrorMessage error={mutation.error} />
      <Button type="submit" disabled={mutation.isPending}>
        {existing ? "Save" : "Add HTTP target"}
      </Button>
    </form>
  );
}
