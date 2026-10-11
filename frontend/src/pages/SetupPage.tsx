import { useState, type FormEvent } from "react";
import { useSetup } from "../auth";
import { Button, CenteredPage, ErrorMessage, PASSWORD_HINT, TextField } from "../components/ui";

export default function SetupPage() {
  const setup = useSetup();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && confirm !== password;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!mismatch) setup.mutate({ username, password });
  }

  return (
    <CenteredPage>
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-semibold tracking-tight">
            <img src="/favicon.svg" alt="" className="h-9 w-9" />
            Welcome to runpad
          </h1>
          <p className="mt-1 text-sm text-muted">
            Create the admin account. This screen is only shown once.
          </p>
        </div>
        <TextField
          label="Username"
          autoComplete="username"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          hint={PASSWORD_HINT}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <ErrorMessage error={mismatch ? new Error("Passwords do not match") : setup.error} />
        <Button type="submit" disabled={setup.isPending || mismatch}>
          Create admin
        </Button>
      </form>
    </CenteredPage>
  );
}
