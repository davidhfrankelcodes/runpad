import { Link, useSearchParams } from "react-router";
import { useRuns } from "../actions";
import { RunStatus } from "../components/RunStatus";
import { duration } from "../format";
import { ErrorMessage } from "../components/ui";

export default function RunsPage() {
  const runs = useRuns();
  const [params] = useSearchParams();
  const actionId = params.get("action");
  const shown = runs.data?.filter((run) => !actionId || run.action_id === actionId);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Runs</h1>
        <p className="text-sm text-zinc-400">
          {actionId ? "History for one action. " : ""}Most recent first.
          {actionId && (
            <Link to="/runs" className="ml-2 underline">
              Show all
            </Link>
          )}
        </p>
      </div>
      <ErrorMessage error={runs.error} />
      {shown?.length === 0 && <p className="text-sm text-zinc-500">No runs yet.</p>}
      {shown && shown.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-900 text-zinc-400">
              <tr>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">By</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2 font-medium">Took</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((run) => (
                <tr key={run.id} className="border-t border-zinc-800 hover:bg-zinc-900/50">
                  <td className="px-4 py-2">
                    <Link to={`/runs/${run.id}`} className="hover:underline">
                      {run.action_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <RunStatus status={run.status} />
                  </td>
                  <td className="px-4 py-2 text-zinc-400">{run.triggered_by}</td>
                  <td className="px-4 py-2 text-zinc-400">
                    {new Date(run.started_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-zinc-400">{duration(run)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
