import { Link, useSearchParams } from "react-router";
import { FeatureIcon } from "../components/FeatureIcon";
import { Button, ErrorMessage, Pager, TextField, Tooltip } from "../components/ui";
import { useDeleteInstance, useFeatureInstances, useFeatures, type FeatureInstance } from "../features";
import { ago } from "../format";
import { TONE_DOT, TONE_MEANING } from "../tones";

const PAGE_SIZE = 25;

/** Every tile: what it checks, its state now, and where it shows. Like Actions, for tiles. */
export default function TilesPage() {
  const features = useFeatures();
  const instances = useFeatureInstances();
  const remove = useDeleteInstance();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const byId = new Map(features.data?.map((f) => [f.id, f]));
  const describe = (tile: FeatureInstance) => {
    const feature = byId.get(tile.feature_id);
    const item = feature?.items.find((i) => i.key === tile.item);
    return { feature, what: feature ? `${feature.name} · ${item?.name ?? tile.item}` : tile.feature_id };
  };
  const tiles = (instances.data ?? []).filter((i) => i.kind === "tile");
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const found = tiles.filter((tile) => {
    const text = [tile.name, describe(tile).what, ...tile.pads.map((p) => p.name), tile.state?.value ?? ""]
      .join(" ")
      .toLowerCase();
    return words.every((word) => text.includes(word));
  });
  const pages = Math.max(1, Math.ceil(found.length / PAGE_SIZE));
  const current = Math.min(page, pages);
  const shown = found.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  // Built from the latest URL, not this render's, so quick successive changes all apply.
  function update(changes: Record<string, string | null>) {
    setParams(
      (latest) => {
        const next = new URLSearchParams(latest);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  }

  function confirmDelete(tile: FeatureInstance) {
    const where = tile.pads.length ? ` It is removed from ${tile.pads.map((p) => p.name).join(", ")}.` : "";
    if (window.confirm(`Delete the tile "${tile.name}"?${where}`)) remove.mutate(tile.id);
  }

  const pager = (
    <Pager
      page={current}
      pageSize={PAGE_SIZE}
      total={found.length}
      onPage={(next) => {
        update({ page: next === 1 ? null : String(next) });
        window.scrollTo({ top: 0 });
      }}
    />
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold">Tiles</h1>
          <p className="text-sm text-muted">Status that pads show, checked on their own.</p>
        </div>
        <Link to="/features?kind=tile">
          <Button tooltip="Pick what the tile checks from the catalog, then fill in a short form.">
            New tile
          </Button>
        </Link>
      </div>
      <ErrorMessage error={features.error ?? instances.error ?? remove.error} />
      {instances.data && tiles.length === 0 && (
        <p className="text-sm text-faint">
          No tiles yet. <Link to="/features?kind=tile" className="underline">Add one</Link> from the
          catalog.
        </p>
      )}
      {tiles.length > 0 && (
        <TextField
          label="Search"
          type="search"
          placeholder="Name, what it checks, pad, state, ..."
          value={query}
          onChange={(e) => update({ q: e.target.value || null, page: null })}
        />
      )}
      {tiles.length > 0 && found.length === 0 && (
        <p className="text-sm text-faint">
          No tiles match.{" "}
          <button type="button" className="underline" onClick={() => update({ q: null, page: null })}>
            Clear the search
          </button>
        </p>
      )}
      {pager}
      <div className="flex flex-col gap-2">
        {shown.map((tile) => {
          const { feature, what } = describe(tile);
          return (
            <div
              key={tile.id}
              className="flex flex-col gap-3 rounded-lg border border-line p-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
            >
              <div className="flex min-w-0 gap-3">
                <FeatureIcon name={feature?.icon ?? "feature"} className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
                <div className="min-w-0">
                  <Link to={`/features/instances/${tile.id}`} className="font-medium hover:underline [overflow-wrap:anywhere]">
                    {tile.name}
                  </Link>
                  <p className="text-sm text-muted">{what}</p>
                  {tile.state ? (
                    <Tooltip
                      className="flex"
                      text={`${TONE_MEANING[tile.state.tone]} Checked ${ago(tile.state.checked_at)}.`}
                    >
                      <span tabIndex={0} className="flex min-w-0 items-center gap-2 text-sm">
                        <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${TONE_DOT[tile.state.tone]}`} />
                        <span className="font-medium">{tile.state.value}</span>
                        {tile.state.detail && <span className="truncate text-faint">{tile.state.detail}</span>}
                      </span>
                    </Tooltip>
                  ) : (
                    <p className="text-sm text-faint">Not checked yet</p>
                  )}
                  <p className="text-xs text-faint">
                    {tile.pads.length ? (
                      <>
                        On{" "}
                        {tile.pads.map((pad, index) => (
                          <span key={pad.id}>
                            {index > 0 && ", "}
                            <Link to={`/pads/${pad.id}`} className="underline">
                              {pad.name}
                            </Link>
                          </span>
                        ))}
                      </>
                    ) : (
                      "On no pad. Add it to one in the pad editor."
                    )}
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <Link to={`/features/instances/${tile.id}`}>
                  <Button variant="secondary" tooltip="Change what it checks. It stays on its pads.">
                    Edit
                  </Button>
                </Link>
                <Link to={`/features/add/${tile.feature_id}/${tile.item}?from=${tile.id}`}>
                  <Button variant="secondary" tooltip="Start a new tile with the same settings, which you can change before adding it.">
                    Clone
                  </Button>
                </Link>
                <Button
                  variant="danger"
                  disabled={remove.isPending}
                  onClick={() => confirmDelete(tile)}
                  tooltip="Delete the tile and remove it from every pad. Run history is kept."
                >
                  Delete
                </Button>
              </div>
            </div>
          );
        })}
      </div>
      {pager}
    </div>
  );
}
