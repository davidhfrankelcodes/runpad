import { useId, useState } from "react";
import { Link } from "react-router";
import { FeatureIcon } from "../components/FeatureIcon";
import { Badge, Button, ErrorMessage, Tooltip } from "../components/ui";
import {
  useDeleteInstance,
  useFeatureInstances,
  useFeatures,
  type CatalogItem,
  type Feature,
  type FeatureInstance,
} from "../features";

/** The catalog, item by item: each card adds exactly one button or one tile. */
export default function FeaturesPage() {
  const features = useFeatures();
  const instances = useFeatureInstances();
  const remove = useDeleteInstance();

  const categories = new Map<string, Feature[]>();
  for (const feature of features.data ?? []) {
    categories.set(feature.category, [...(categories.get(feature.category) ?? []), feature]);
  }
  const inUse = new Map<string, FeatureInstance[]>();
  for (const instance of instances.data ?? []) {
    const key = `${instance.feature_id}/${instance.item}`;
    inUse.set(key, [...(inUse.get(key) ?? []), instance]);
  }
  // Instances of features or items this version no longer has; they can still be deleted.
  const known = new Set(
    features.data?.flatMap((f) => f.items.map((item) => `${f.id}/${item.key}`)),
  );
  const orphans = features.data
    ? (instances.data ?? []).filter((i) => !known.has(`${i.feature_id}/${i.item}`))
    : [];

  function confirmDelete(instance: FeatureInstance) {
    const message = `Delete "${instance.name}" and the button or tile it added? Run history is kept.`;
    if (window.confirm(message)) remove.mutate(instance.id);
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Features</h1>
        <p className="text-sm text-muted">
          Ready-made buttons and status tiles. Pick one, fill in a short form, and runpad adds
          exactly that button or tile.
        </p>
      </div>
      <ErrorMessage error={features.error ?? instances.error ?? remove.error} />

      {[...categories].map(([category, items]) => (
        <section key={category} className="flex flex-col gap-4">
          <h2 className="text-base font-semibold">{category}</h2>
          {items.map((feature) => (
            <div key={feature.id} className="flex flex-col gap-2">
              <div className="flex items-start gap-2">
                <FeatureIcon name={feature.icon} className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
                <div>
                  <h3 className="text-sm font-medium">{feature.name}</h3>
                  <p className="text-xs text-muted">{feature.description}</p>
                </div>
              </div>
              <div className="grid items-start gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {feature.items.map((item) => (
                  <ItemCard
                    key={item.key}
                    feature={feature}
                    item={item}
                    instances={inUse.get(`${feature.id}/${item.key}`) ?? []}
                    onDelete={confirmDelete}
                    deleting={remove.isPending}
                  />
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}

      {orphans.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">No longer in the catalog</h2>
          <p className="text-sm text-muted">
            This version of runpad does not have these. Their buttons cannot run; delete them to
            clean up.
          </p>
          <InstanceList instances={orphans} onDelete={confirmDelete} deleting={remove.isPending} />
        </section>
      )}
    </div>
  );
}

const KIND_TIPS = {
  button: "Adds one button to a pad.",
  tile: "Adds one status tile to a pad. It updates on its own.",
};

function ItemCard({
  feature,
  item,
  instances,
  onDelete,
  deleting,
}: {
  feature: Feature;
  item: CatalogItem;
  instances: FeatureInstance[];
  onDelete: (instance: FeatureInstance) => void;
  deleting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div className="flex flex-col rounded-lg border border-line">
      <Link
        to={`/features/add/${feature.id}/${item.key}`}
        className="flex flex-col gap-1 rounded-lg p-3 hover:bg-card"
        aria-label={`Add ${feature.name}: ${item.name} ${item.kind}`}
      >
        <span className="flex items-center justify-between gap-2">
          <span className="font-medium">{item.name}</span>
          <Badge tooltip={KIND_TIPS[item.kind]}>{item.kind}</Badge>
        </span>
        <span className="text-sm text-muted">{item.description}</span>
      </Link>
      {instances.length > 0 && (
        <div className="border-t border-line px-3 py-2">
          <Tooltip text="Show the ones you have added, to change or delete them.">
            <button
              type="button"
              aria-expanded={open}
              aria-controls={listId}
              onClick={() => setOpen(!open)}
              className="flex items-center gap-1.5 text-sm text-link hover:underline"
            >
              <span aria-hidden="true" className={`inline-block transition-transform ${open ? "rotate-90" : ""}`}>
                ›
              </span>
              {instances.length} in use
            </button>
          </Tooltip>
          {open && (
            <div id={listId} className="mt-2">
              <InstanceList instances={instances} onDelete={onDelete} deleting={deleting} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function InstanceList({
  instances,
  onDelete,
  deleting,
}: {
  instances: FeatureInstance[];
  onDelete: (instance: FeatureInstance) => void;
  deleting: boolean;
}) {
  return (
    <ul className="flex flex-col divide-y divide-line">
      {instances.map((instance) => (
        <li key={instance.id} className="flex items-center justify-between gap-3 py-1.5">
          <Link
            to={`/features/instances/${instance.id}`}
            className="min-w-0 truncate text-sm hover:underline"
          >
            {instance.name}
          </Link>
          <div className="flex shrink-0 gap-2">
            <Link to={`/features/instances/${instance.id}`}>
              <Button
                variant="secondary"
                size="sm"
                tooltip="Change its settings. Its button or tile and run history stay attached."
              >
                Edit
              </Button>
            </Link>
            <Button
              variant="danger"
              size="sm"
              disabled={deleting}
              onClick={() => onDelete(instance)}
              tooltip="Delete it with the button or tile it added. Run history is kept."
            >
              Delete
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
