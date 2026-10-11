import { Link, useSearchParams } from "react-router";
import { useRuns } from "../actions";
import { RunStatus } from "../components/RunStatus";
import { duration } from "../format";
import { ErrorMessage, Pager, SelectField } from "../components/ui";
import { RETENTION_CHOICES, useAppSettings, useUpdateAppSettings } from "../appSettings";
import { useCurrentUser } from "../auth";

export default function RunsPage() {
  const [params, setParams] = useSearchParams();
  const actionId = params.get("action") ?? undefined;
  const page = Math.max(1, Number(params.get("page")) || 1);
  const runs = useRuns({ page, actionId });
  const shown = runs.data?.runs;
  const total = runs.data?.total ?? 0;
  const pageSize = runs.data?.page_size ?? 1;

  function goTo(next: number) {
    setParams((latest) => {
      const updated = new URLSearchParams(latest);
      if (next === 1) updated.delete("page");
      else updated.set("page", String(next));
      return updated;
    });
    window.scrollTo({ top: 0 });
  }

  const pager = (
    <Pager
      page={page}
      pageSize={pageSize}
      total={total}
      onPage={goTo}
      previous="Newer"
      next="Older"
      previousTip="Later runs."
      nextTip="Earlier runs."
    />
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
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
        <Retention />
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

function retentionLabel(days: number | null): string {
  return RETENTION_CHOICES.find((c) => c.days === days)?.label.toLowerCase() ?? `${days} days`;
}

/** How long runs are kept: admins choose, members see it. */
function Retention() {
  const user = useCurrentUser();
  const settings = useAppSettings();
  const update = useUpdateAppSettings();
  if (!settings.data) return <ErrorMessage error={settings.error} />;
  const days = settings.data.run_retention_days;

  if (user.role !== "admin") {
    return (
      <p className="text-sm text-faint">
        {days === null ? "Runs are kept forever." : `Runs are kept for ${retentionLabel(days)}.`}
      </p>
    );
  }

  function choose(value: string) {
    const next = value === "forever" ? null : Number(value);
    const shorter = next !== null && (days === null || next < days);
    if (
      shorter &&
      !window.confirm(
        `Keep runs for ${retentionLabel(next)}? Finished runs older than that are deleted now, with their output.`,
      )
    ) {
      return;
    }
    update.mutate({ run_retention_days: next as typeof days });
  }

  return (
    <div className="flex flex-col gap-1">
      <SelectField
        label="Keep runs for"
        value={days === null ? "forever" : String(days)}
        disabled={update.isPending}
        onChange={(e) => choose(e.target.value)}
        hint="Older finished runs are deleted every hour. Applies to everyone."
      >
        {RETENTION_CHOICES.map((choice) => (
          <option key={choice.label} value={choice.days === null ? "forever" : String(choice.days)}>
            {choice.label}
          </option>
        ))}
      </SelectField>
      <ErrorMessage error={update.error} />
    </div>
  );
}
