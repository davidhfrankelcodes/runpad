import { Link } from "react-router";
import { FeatureIcon } from "../components/FeatureIcon";
import { Button, ErrorMessage } from "../components/ui";
import { useDeleteInstance, useFeatureInstances, useFeatures, type Feature } from "../features";

export default function FeaturesPage() {
  const features = useFeatures();
  const instances = useFeatureInstances();
  const remove = useDeleteInstance();
  const byId = new Map(features.data?.map((f) => [f.id, f]));

  const categories = new Map<string, Feature[]>();
  for (const feature of features.data ?? []) {
    categories.set(feature.category, [...(categories.get(feature.category) ?? []), feature]);
  }

  function confirmDelete(id: string, name: string) {
    if (window.confirm(`Delete "${name}" and the actions and buttons it created? Run history is kept.`)) {
      remove.mutate(id);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-lg font-semibold">Features</h1>
        <p className="text-sm text-zinc-400">
          Ready-made buttons for common tasks. Fill in a short form and runpad creates the
          actions and buttons.
        </p>
      </div>
      <ErrorMessage error={features.error ?? instances.error ?? remove.error} />

      <section className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">Enabled</h2>
        {instances.data?.length === 0 && (
          <p className="text-sm text-zinc-500">Nothing enabled yet. Pick a feature below.</p>
        )}
        {instances.data?.map((instance) => {
          const feature = byId.get(instance.feature_id);
          return (
            <div
              key={instance.id}
              className="flex items-center justify-between gap-4 rounded-lg border border-zinc-800 p-4"
            >
              <div className="flex min-w-0 items-center gap-3">
                <FeatureIcon name={feature?.icon ?? ""} className="h-6 w-6 shrink-0 text-zinc-400" />
                <div className="min-w-0">
                  <Link to={`/features/instances/${instance.id}`} className="font-medium hover:underline">
                    {instance.name}
                  </Link>
                  <p className="text-sm text-zinc-400">
                    {feature?.name ?? `Unknown feature (${instance.feature_id})`}
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <Link to={`/features/instances/${instance.id}`}>
                  <Button variant="secondary">Edit</Button>
                </Link>
                <Button
                  variant="danger"
                  disabled={remove.isPending}
                  onClick={() => confirmDelete(instance.id, instance.name)}
                >
                  Delete
                </Button>
              </div>
            </div>
          );
        })}
      </section>

      {[...categories].map(([category, items]) => (
        <section key={category} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{category}</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {items.map((feature) => (
              <Link
                key={feature.id}
                to={`/features/add/${feature.id}`}
                className="flex gap-3 rounded-lg border border-zinc-800 p-4 hover:border-zinc-600 hover:bg-zinc-900"
              >
                <FeatureIcon name={feature.icon} className="h-8 w-8 shrink-0 text-emerald-400" />
                <div>
                  <p className="font-medium">{feature.name}</p>
                  <p className="text-sm text-zinc-400">{feature.description}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
