import { useState, type FormEvent } from "react";
import { useChangePassword, useCurrentUser } from "../auth";
import { Button, Card, ErrorMessage, PASSWORD_HINT, TextField } from "../components/ui";

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
        <p className="text-sm text-zinc-400">Role: {user.role}</p>
      </div>
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
            <p className="text-sm text-emerald-400">Password changed.</p>
          )}
          <Button type="submit" disabled={changePassword.isPending}>
            Change password
          </Button>
        </form>
      </Card>
    </div>
  );
}
