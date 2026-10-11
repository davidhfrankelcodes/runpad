import { Link, useSearchParams } from "react-router";
import { useRuns } from "../actions";
import { RunStatus } from "../components/RunStatus";
import { duration } from "../format";
import { Button, ErrorMessage } from "../components/ui";

export default function RunsPage() {
  const [params, setParams] = useSearchParams();
  const actionId = params.get("action") ?? undefined;
  const page = Math.max(1, Number(params.get("page")) || 1);
  const runs = useRuns({ page, actionId });
  const shown = runs.data?.runs;
  const total = runs.data?.total ?? 0;
  const pageSize = runs.data?.page_size ?? 1;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  function goTo(next: number) {
    const updated = new URLSearchParams(params);
    if (next === 1) updated.delete("page");
    else updated.set("page", String(next));
    setParams(updated);
    window.scrollTo({ top: 0 });
  }

  const pager = total > pageSize && (
    <nav aria-label="Pages" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-muted">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()}
      </span>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          disabled={page <= 1}
          onClick={() => goTo(page - 1)}
          tooltip="Later runs."
        >
          ← Newer
        </Button>
        <span className="text-muted">
          Page {page} of {pages}
        </span>
        <Button
          variant="secondary"
          disabled={page >= pages}
          onClick={() => goTo(page + 1)}
          tooltip="Earlier runs."
        >
          Older →
        </Button>
      </div>
    </nav>
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold">Runs</h1>
        <p className="text-sm text-muted">
          {actionId ? "History for one action. " : ""}Most recent first.
          {actionId && (
            <Link to="/runs" className="ml-2 underline">
              Show all
            </Link>
          )}
        </p>
      </div>
      <ErrorMessage error={runs.error} />
      {shown?.length === 0 &&
        (page > 1 ? (
          <p className="text-sm text-faint">
            No runs on this page.{" "}
            <button type="button" className="underline" onClick={() => goTo(1)}>
              Back to the first page
            </button>
          </p>
        ) : (
          <p className="text-sm text-faint">No runs yet.</p>
        ))}
      {pager}
      {shown && shown.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-sm">
            <thead className="bg-card-header text-muted">
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
                <tr key={run.id} className="border-t border-line hover:bg-raised">
                  <td className="px-4 py-2">
                    <Link to={`/runs/${run.id}`} className="hover:underline">
                      {run.action_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <RunStatus status={run.status} />
                  </td>
                  <td className="px-4 py-2 text-muted">{run.triggered_by}</td>
                  <td className="px-4 py-2 text-muted">
                    {new Date(run.started_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-muted">{duration(run)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pager}
    </div>
  );
}
