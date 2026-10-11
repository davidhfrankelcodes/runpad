import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useActions, useRunAction, type Action } from "../actions";
import { RunDialog } from "../components/RunDialog";
import { Badge, Button, ErrorMessage } from "../components/ui";

export default function ActionsPage() {
  const actions = useActions();
  const [running, setRunning] = useState<Action | null>(null);
  const run = useRunAction();
  const navigate = useNavigate();

  function press(action: Action) {
    // Only ask first when there is something to fill in or confirm.
    if (action.args.length > 0 || action.confirm) {
      setRunning(action);
    } else {
      run.mutate(
        { id: action.id, args: {} },
        { onSuccess: (started) => void navigate(`/runs/${started.id}`) },
      );
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Actions</h1>
          <p className="text-sm text-zinc-400">Commands that buttons run.</p>
        </div>
        <Link to="/actions/new">
          <Button>New action</Button>
        </Link>
      </div>
      <ErrorMessage error={actions.error ?? run.error} />
      {actions.data?.length === 0 && <p className="text-sm text-zinc-500">No actions yet.</p>}
      <div className="flex flex-col gap-2">
        {actions.data?.map((action) => (
          <div
            key={action.id}
            className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 p-4"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Link to={`/actions/${action.id}`} className="font-medium hover:underline">
                  {action.name}
                </Link>
                <Badge>{action.executor}</Badge>
                {action.confirm && <Badge>confirm</Badge>}
              </div>
              {action.description && (
                <p className="truncate text-sm text-zinc-400">{action.description}</p>
              )}
            </div>
            <Button disabled={run.isPending} onClick={() => press(action)}>
              Run
            </Button>
          </div>
        ))}
      </div>
      {running && <RunDialog action={running} onClose={() => setRunning(null)} />}
    </div>
  );
}
