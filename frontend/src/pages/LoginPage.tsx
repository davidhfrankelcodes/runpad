import { useState, type FormEvent } from "react";
import { useLogin } from "../auth";
import { Button, CenteredPage, ErrorMessage, TextField } from "../components/ui";

export default function LoginPage() {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ username, password });
  }

  return (
    <CenteredPage>
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">runpad</h1>
        <TextField
          label="Username"
          autoComplete="username"
          required
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorMessage error={login.error} />
        <Button type="submit" disabled={login.isPending}>
          Log in
        </Button>
      </form>
    </CenteredPage>
  );
}
