import { Link, useLocation, useNavigate, useParams } from "react-router";
import { useRun } from "../actions";
import { RunOutput } from "../components/RunOutput";
import { Button, CloseLabel } from "../components/ui";
import { useCurrentUser } from "../auth";

export default function RunPage() {
  const { id = "" } = useParams();
  const run = useRun(id);
  const user = useCurrentUser();
  const navigate = useNavigate();
  const location = useLocation();
  const actionId = run.data?.action_id;

  // Back to where the run was opened from; straight to Runs when this page was opened directly.
  function close() {
    if (location.key === "default") void navigate("/runs");
    else void navigate(-1);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button variant="secondary" onClick={close} tooltip="Leave this run and go back.">
          <CloseLabel />
        </Button>
      </div>
      <RunOutput key={id} id={id} />
      {actionId && user.role === "admin" && (
        <Link to={`/runs?action=${actionId}`} className="text-sm text-muted underline">
          History for this action
        </Link>
      )}
    </div>
  );
}
