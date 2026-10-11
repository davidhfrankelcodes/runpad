import { useState, type FormEvent } from "react";
import { useChangePassword, useCurrentUser } from "../auth";
import { Button, Card, ErrorMessage, PASSWORD_HINT, SelectField, TextField } from "../components/ui";
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
