import { useId, useState } from "react";
import { Link } from "react-router";
import { FeatureIcon } from "../components/FeatureIcon";
import { Button, ErrorMessage, Tooltip } from "../components/ui";
import {
  useDeleteInstance,
  useFeatureInstances,
  useFeatures,
  type Feature,
  type FeatureInstance,
} from "../features";

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
    inUse.set(instance.feature_id, [...(inUse.get(instance.feature_id) ?? []), instance]);
  }
  // Instances of features this version no longer has; they can still be deleted.
  const known = new Set(features.data?.map((f) => f.id));
  const orphans = features.data ? (instances.data ?? []).filter((i) => !known.has(i.feature_id)) : [];

  function confirmDelete(instance: FeatureInstance) {
    const message = `Delete "${instance.name}" and the actions and buttons it created? Run history is kept.`;
    if (window.confirm(message)) remove.mutate(instance.id);
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Features</h1>
        <p className="text-sm text-muted">
          Ready-made buttons and status tiles for common tasks. Fill in a short form and runpad
          creates them.
        </p>
      </div>
      <ErrorMessage error={features.error ?? instances.error ?? remove.error} />

      {[...categories].map(([category, items]) => (
        <section key={category} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{category}</h2>
          <div className="grid items-start gap-3 sm:grid-cols-2">
            {items.map((feature) => (
              <FeatureCard
                key={feature.id}
                feature={feature}
                instances={inUse.get(feature.id) ?? []}
                onDelete={confirmDelete}
                deleting={remove.isPending}
              />
            ))}
          </div>
        </section>
      ))}

      {orphans.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">No longer in the catalog</h2>
          <p className="text-sm text-muted">
            This version of runpad does not have these features. Their buttons cannot run; delete
            them to clean up.
          </p>
          <InstanceList instances={orphans} onDelete={confirmDelete} deleting={remove.isPending} />
        </section>
      )}
    </div>
  );
}

function FeatureCard({
  feature,
  instances,
  onDelete,
  deleting,
}: {
  feature: Feature;
  instances: FeatureInstance[];
  onDelete: (instance: FeatureInstance) => void;
  deleting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div className="flex flex-col rounded-lg border border-line">
      <Link
        to={`/features/add/${feature.id}`}
        className="flex gap-3 rounded-lg p-4 hover:bg-card"
        aria-label={`Add ${feature.name}`}
      >
        <FeatureIcon name={feature.icon} className="h-8 w-8 shrink-0 text-accent" />
        <div>
          <p className="font-medium">{feature.name}</p>
          <p className="text-sm text-muted">{feature.description}</p>
        </div>
      </Link>
      {instances.length > 0 && (
        <div className="border-t border-line px-4 py-2">
          <Tooltip text="Show the ones you have set up, to change or delete them.">
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
                tooltip="Change its settings. Its buttons and run history stay attached."
              >
                Edit
              </Button>
            </Link>
            <Button
              variant="danger"
              size="sm"
              disabled={deleting}
              onClick={() => onDelete(instance)}
              tooltip="Delete it with the actions, buttons, and tiles it created. Run history is kept."
            >
              Delete
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
