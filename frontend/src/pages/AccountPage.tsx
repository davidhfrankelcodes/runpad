import { useState, type FormEvent } from "react";
import { useChangePassword, useCurrentUser } from "../auth";
import {
  Button,
  Card,
  CopyableText,
  ErrorMessage,
  PASSWORD_HINT,
  SelectField,
  TextField,
} from "../components/ui";
import { ago } from "../format";
import {
  useApiTokens,
  useCreateApiToken,
  useRevokeApiToken,
  type ApiToken,
  type ApiTokenCreate,
} from "../tokens";
import { useAppearance, useSetTheme, useThemeOptions, type ThemeOption } from "../theme";

export default function AccountPage() {
  const user = useCurrentUser();
  const changePassword = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    changePassword.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
        },
      },
    );
  }

  return (
    <div className="flex max-w-md flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">{user.username}</h1>
        <p className="text-sm text-muted">Role: {user.role}</p>
      </div>
      <AppearanceCard />
      <ApiTokensCard />
      <Card title="Change password">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            hint={`${PASSWORD_HINT} Your other sessions will be logged out.`}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <ErrorMessage error={changePassword.error} />
          {changePassword.isSuccess && (
            <p className="text-sm text-link">Password changed.</p>
          )}
          <Button type="submit" disabled={changePassword.isPending}>
            Change password
          </Button>
        </form>
      </Card>
    </div>
  );
}

function AppearanceCard() {
  const user = useCurrentUser();
  const appearance = useAppearance();
  const url = appearance.data?.themepark_url;
  const options = useThemeOptions(url);
  const setTheme = useSetTheme();
  const groups = new Map<ThemeOption["group"], ThemeOption[]>();
  for (const option of options.data ?? []) {
    groups.set(option.group, [...(groups.get(option.group) ?? []), option]);
  }

  return (
    <Card title="Appearance">
      <div className="flex flex-col gap-3">
        <SelectField
          label="Theme"
          value={user.theme ?? ""}
          disabled={setTheme.isPending}
          onChange={(e) => setTheme.mutate(e.target.value || null)}
          hint={
            <>
              Themes by{" "}
              <a href="https://theme-park.dev" target="_blank" rel="noreferrer" className="underline">
                theme.park
              </a>
              , loaded from {url ?? "theme.park"}. Applies to you only.
            </>
          }
        >
          <option value="">runpad (default)</option>
          {/* Keep a saved theme selectable even if the list is unavailable. */}
          {user.theme && !options.data?.some((o) => o.id === user.theme) && (
            <option value={user.theme}>{user.theme}</option>
          )}
          {[...groups].map(([group, items]) => (
            <optgroup key={group} label={group}>
              {items.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </optgroup>
          ))}
        </SelectField>
        <ErrorMessage error={options.error ?? setTheme.error} />
      </div>
    </Card>
  );
}

const EXPIRY_CHOICES: { label: string; days: ApiTokenCreate["expires_in_days"] }[] = [
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
  { label: "Never", days: null },
];

function expiryText(token: ApiToken): string {
  if (!token.expires_at) return "Never expires";
  const expires = new Date(token.expires_at);
  return expires.getTime() <= Date.now()
    ? `Expired ${expires.toLocaleDateString()}`
    : `Expires ${expires.toLocaleDateString()}`;
}

/** Personal API tokens: create one (shown once), see when each was used, revoke. */
function ApiTokensCard() {
  const tokens = useApiTokens();
  const create = useCreateApiToken();
  const revoke = useRevokeApiToken();
  const [name, setName] = useState("");
  const [expiry, setExpiry] = useState("30");
  const [created, setCreated] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const days = expiry === "never" ? null : (Number(expiry) as ApiTokenCreate["expires_in_days"]);
    create.mutate(
      { name, expires_in_days: days },
      {
        onSuccess: (token) => {
          setCreated(token.token);
          setName("");
        },
      },
    );
  }

  function confirmRevoke(token: ApiToken) {
    if (window.confirm(`Revoke "${token.name}"? Anything using it stops working at once.`)) {
      revoke.mutate(token.id);
    }
  }

  return (
    <Card title="API tokens">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          Use runpad from scripts and other tools. A token acts as you, with your role. Send it
          as <code className="font-mono text-xs">Authorization: Bearer &lt;token&gt;</code>; the{" "}
          <a href="/api/v1/docs" target="_blank" rel="noreferrer" className="underline">
            API docs
          </a>{" "}
          list every endpoint.
        </p>
        {created && (
          <div className="flex flex-col gap-2 rounded-md border border-line-strong p-3">
            <CopyableText label="Your new token" value={created} />
            <p className="text-xs text-faint">
              Copy it now: it is shown only once. runpad keeps only a hash of it.
            </p>
            <Button type="button" variant="secondary" onClick={() => setCreated(null)}>
              Done
            </Button>
          </div>
        )}
        <form onSubmit={submit} className="flex flex-col gap-3">
          <TextField
            label="Name"
            required
            maxLength={64}
            placeholder="Home Assistant, backup script, ..."
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <SelectField
            label="Expires after"
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
          >
            {EXPIRY_CHOICES.map((choice) => (
              <option key={choice.label} value={choice.days === null ? "never" : String(choice.days)}>
                {choice.label}
              </option>
            ))}
          </SelectField>
          <ErrorMessage error={create.error ?? revoke.error ?? tokens.error} />
          <Button
            type="submit"
            disabled={create.isPending}
            tooltip="Creates the token and shows it once."
          >
            Create token
          </Button>
        </form>
        {tokens.data && tokens.data.length > 0 && (
          <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
            {tokens.data.map((token) => (
              <li key={token.id} className="flex items-center justify-between gap-3 p-3">
                <div className="min-w-0 text-sm">
                  <p className="truncate font-medium">{token.name}</p>
                  <p className="font-mono text-xs text-muted">{token.prefix}…</p>
                  <p className="text-xs text-faint">
                    {expiryText(token)} ·{" "}
                    {token.last_used_at ? `last used ${ago(token.last_used_at)}` : "never used"}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="danger"
                  disabled={revoke.isPending}
                  onClick={() => confirmRevoke(token)}
                  tooltip="Delete this token. Anything using it stops working at once."
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
