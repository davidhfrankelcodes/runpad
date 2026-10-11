import { useState, type FormEvent } from "react";
import type { Role, User } from "../api/client";
import { useCurrentUser } from "../auth";
import { Button, Card, ErrorMessage, PASSWORD_HINT, TextField } from "../components/ui";
import { useCreateUser, useUpdateUser, useUsers } from "../users";

export default function UsersPage() {
  const users = useUsers();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-lg font-semibold">Users</h1>
      <ErrorMessage error={users.error} />
      {users.data && (
        <div className="overflow-hidden rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-card-header text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Username</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {users.data.map((user) => (
                <UserRow key={user.id} user={user} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CreateUserForm />
    </div>
  );
}

function UserRow({ user }: { user: User }) {
  const me = useCurrentUser();
  const update = useUpdateUser();
  const [resetting, setResetting] = useState(false);
  const [password, setPassword] = useState("");

  function resetPassword(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      { id: user.id, password },
      {
        onSuccess: () => {
          setResetting(false);
          setPassword("");
        },
      },
    );
  }

  return (
    <>
      <tr className="border-t border-line">
        <td className="px-4 py-2">
          {user.username}
          {user.id === me.id && <span className="ml-2 text-xs text-faint">(you)</span>}
        </td>
        <td className="px-4 py-2">
          <select
            aria-label={`Role for ${user.username}`}
            className="rounded border border-line-strong bg-input px-2 py-1"
            value={user.role}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ id: user.id, role: e.target.value as Role })}
          >
            <option value="admin">admin</option>
            <option value="member">member</option>
          </select>
        </td>
        <td className={`px-4 py-2 ${user.is_active ? "text-link" : "text-faint"}`}>
          {user.is_active ? "active" : "deactivated"}
        </td>
        <td className="flex justify-end gap-2 px-4 py-2">
          <Button variant="secondary" onClick={() => setResetting(!resetting)}>
            Reset password
          </Button>
          <Button
            variant={user.is_active ? "danger" : "secondary"}
            disabled={update.isPending}
            onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}
          >
            {user.is_active ? "Deactivate" : "Activate"}
          </Button>
        </td>
      </tr>
      {(resetting || update.error) && (
        <tr>
          <td colSpan={4} className="px-4 pb-3">
            <ErrorMessage error={update.error} />
            {resetting && (
              <form onSubmit={resetPassword} className="mt-2 flex items-end gap-2">
                <div className="flex-1">
                  <TextField
                    label={`New password for ${user.username}`}
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={12}
                    hint={`${PASSWORD_HINT} Logs ${user.username} out everywhere.`}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={update.isPending} className="mb-5">
                  Save
                </Button>
              </form>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function CreateUserForm() {
  const create = useCreateUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("member");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { username, password, role },
      {
        onSuccess: () => {
          setUsername("");
          setPassword("");
          setRole("member");
        },
      },
    );
  }

  return (
    <Card title="Add user">
      <form onSubmit={submit} className="flex max-w-md flex-col gap-4">
        <TextField
          label="Username"
          autoComplete="off"
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
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-soft">Role</span>
          <select
            className="rounded-md border border-line-strong bg-input px-3 py-2"
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            <option value="member">member: press buttons on pads they can see</option>
            <option value="admin">admin: configure everything</option>
          </select>
        </label>
        <ErrorMessage error={create.error} />
        <Button type="submit" disabled={create.isPending}>
          Add user
        </Button>
      </form>
    </Card>
  );
}
