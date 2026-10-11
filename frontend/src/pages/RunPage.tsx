import { Link, useParams } from "react-router";
import { useRun } from "../actions";
import { RunOutput } from "../components/RunOutput";
import { useCurrentUser } from "../auth";

export default function RunPage() {
  const { id = "" } = useParams();
  const run = useRun(id);
  const user = useCurrentUser();
  const actionId = run.data?.action_id;

  return (
    <div className="flex flex-col gap-4">
      <RunOutput key={id} id={id} />
      {actionId && user.role === "admin" && (
        <Link to={`/runs?action=${actionId}`} className="text-sm text-muted underline">
          History for this action
        </Link>
      )}
    </div>
  );
}
