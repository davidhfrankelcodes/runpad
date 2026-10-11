import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { needsDialog, useActions, useRunAction, type Action } from "../actions";
import { RunDialog } from "../components/RunDialog";
import { Badge, Button, ErrorMessage } from "../components/ui";

const EXECUTOR_TIPS: Record<Action["executor"], string> = {
  local: "Runs inside the runpad container. It cannot reach the host.",
  ssh: "Runs on an SSH target.",
  http: "Sends an HTTP request to an HTTP target.",
};

export default function ActionsPage() {
  const actions = useActions();
  const [running, setRunning] = useState<Action | null>(null);
  const run = useRunAction();
  const navigate = useNavigate();

  function press(action: Action) {
    // Only ask first when there is something to fill in or confirm.
    if (needsDialog(action)) {
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
          <p className="text-sm text-muted">Commands that buttons run.</p>
        </div>
        <Link to="/actions/new">
          <Button tooltip="Write a command by hand. To put it on a pad, add a button for it in the pad editor.">New action</Button>
        </Link>
      </div>
      <ErrorMessage error={actions.error ?? run.error} />
      {actions.data?.length === 0 && <p className="text-sm text-faint">No actions yet.</p>}
      <div className="flex flex-col gap-2">
        {actions.data?.map((action) => (
          <div
            key={action.id}
            className="flex flex-col gap-3 rounded-lg border border-line p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Link to={`/actions/${action.id}`} className="font-medium hover:underline">
                  {action.name}
                </Link>
                <Badge tooltip={EXECUTOR_TIPS[action.executor]}>{action.executor}</Badge>
                {action.feature_instance_id && (
                  <Badge tooltip="Created by a feature. Change it on the Features page.">feature</Badge>
                )}
                {action.confirm && (
                  <Badge tooltip="Asks for confirmation before running.">confirm</Badge>
                )}
              </div>
              {action.description && (
                <p className="truncate text-sm text-muted">{action.description}</p>
              )}
            </div>
            <div className="flex shrink-0 gap-2">
              {action.feature_instance_id ? (
                <Link to={`/features/instances/${action.feature_instance_id}`}>
                  <Button
                    variant="secondary"
                    tooltip="A feature created this action; change it through the feature's settings."
                  >
                    Edit feature
                  </Button>
                </Link>
              ) : (
                <Link to={`/actions/${action.id}`}>
                  <Button variant="secondary" tooltip="Change the command, arguments, and settings.">
                    Edit
                  </Button>
                </Link>
              )}
              <Link to={`/actions/new?clone=${action.id}`}>
                <Button
                  variant="secondary"
                  tooltip={
                    action.feature_instance_id
                      ? "Start a new custom action from a copy of this one, which you can then edit freely."
                      : "Start a new action from a copy of this one. Nothing is saved until you create it."
                  }
                >
                  Clone
                </Button>
              </Link>
              <Button
                disabled={run.isPending}
                onClick={() => press(action)}
                tooltip={
                  needsDialog(action)
                    ? "Runs the action: asks for arguments or confirmation first."
                    : "Runs the action right away and opens its output."
                }
              >
                <span className="flex items-center gap-1.5">
                  <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3.5 w-3.5 fill-current">
                    <path d="M7 4.5v15l12-7.5-12-7.5Z" />
                  </svg>
                  Run
                </span>
              </Button>
            </div>
          </div>
        ))}
      </div>
      {running && (
        <RunDialog
          action={running}
          onClose={() => setRunning(null)}
          onStarted={(started) => void navigate(`/runs/${started.id}`)}
        />
      )}
    </div>
  );
}
