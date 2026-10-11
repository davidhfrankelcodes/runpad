import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { useCurrentUser } from "../auth";
import { Button, Card, ErrorMessage, TextField } from "../components/ui";
import { useCreatePad, usePads } from "../pads";

/** Home: opens the first pad, or offers to create one. */
export default function PadsPage() {
  const pads = usePads();
  const user = useCurrentUser();

  if (pads.error) return <ErrorMessage error={pads.error} />;
  if (!pads.data) return null;
  const [first] = pads.data;
  if (first) return <Navigate to={`/pads/${first.id}`} replace />;

  return user.role === "admin" ? (
    <div className="mx-auto mt-12 w-full max-w-md">
      <NewPadForm />
    </div>
  ) : (
    <p className="mt-12 text-center text-faint">
      No pads have been shared with you yet. Ask an admin.
    </p>
  );
}

export function NewPadForm({ onCreated }: { onCreated?: () => void }) {
  const create = useCreatePad();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      { name },
      {
        onSuccess: (pad) => {
          setName("");
          onCreated?.();
          void navigate(`/pads/${pad.id}`);
        },
      },
    );
  }

  return (
    <Card title="New pad">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">A pad is a page of buttons and status tiles.</p>
        <TextField
          label="Name"
          required
          placeholder="Home lab"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <ErrorMessage error={create.error} />
        <Button type="submit" disabled={create.isPending}>
          Create pad
        </Button>
      </form>
    </Card>
  );
}
