import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useActions } from "../actions";
import { ConfigForm } from "../components/ConfigForm";
import { FeatureIcon } from "../components/FeatureIcon";
import { Button, Card, ErrorMessage, SelectField, TextField } from "../components/ui";
import {
  configFields,
  initialValues,
  useCreateInstance,
  useDeleteInstance,
  useFeatureInstances,
  useFeatures,
  useUpdateInstance,
  type CatalogItem,
  type Feature,
  type FeatureInstance,
} from "../features";
import { usePads } from "../pads";

/** Add one item (/features/add/:featureId/:item) or edit an instance
 * (/features/instances/:id). */
export default function FeatureInstancePage() {
  const { featureId, item: itemKey, id } = useParams();
  const features = useFeatures();
  const instances = useFeatureInstances();
  const instance = id ? instances.data?.find((i) => i.id === id) : undefined;
  const feature = features.data?.find((f) => f.id === (instance?.feature_id ?? featureId));
  const item = feature?.items.find((i) => i.key === (instance?.item ?? itemKey));

  const error = features.error ?? instances.error;
  if (error) return <ErrorMessage error={error} />;
  if (!features.data || !instances.data) return null;
  if (id && !instance) return <ErrorMessage error={new Error("Feature instance not found")} />;
  if (!feature || !item) return <ErrorMessage error={new Error("Unknown feature item")} />;
  return (
    <InstanceForm
      key={id ?? `${featureId}/${itemKey}`}
      feature={feature}
      item={item}
      existing={instance}
      siblings={instances.data.filter((i) => i.feature_id === feature.id && i.id !== id)}
    />
  );
}

function InstanceForm({
  feature,
  item,
  existing,
  siblings,
}: {
  feature: Feature;
  item: CatalogItem;
  existing?: FeatureInstance;
  siblings: FeatureInstance[];
}) {
  const fields = configFields(feature);
  const create = useCreateInstance();
  const update = useUpdateInstance();
  const remove = useDeleteInstance();
  const pads = usePads();
  const navigate = useNavigate();

  const [name, setName] = useState(existing?.name ?? "");
  const [values, setValues] = useState(() => initialValues(fields, existing?.config));
  // undefined until chosen: defaults to the first pad once pads have loaded.
  const [padChoice, setPadChoice] = useState<string>();
  const padId = padChoice ?? pads.data?.[0]?.id ?? "";
  const tile = item.kind === "tile";

  function submit(event: FormEvent) {
    event.preventDefault();
    const label = name.trim() || null;
    if (existing) {
      update.mutate(
        { id: existing.id, name: label ?? existing.name, config: values },
        { onSuccess: () => void navigate("/features") },
      );
      return;
    }
    create.mutate(
      { feature_id: feature.id, item: item.key, name: label, config: values, pad_id: padId || null },
      { onSuccess: () => void navigate(padId ? `/pads/${padId}` : "/features") },
    );
  }

  function confirmDelete() {
    if (!existing) return;
    if (window.confirm(`Delete "${existing.name}" and the ${item.kind} it added? Run history is kept.`)) {
      remove.mutate(existing.id, { onSuccess: () => void navigate("/features") });
    }
  }

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <FeatureIcon name={feature.icon} className="h-8 w-8 text-accent" />
        <div>
          <h1 className="text-lg font-semibold">
            {existing ? `Edit ${existing.name}` : `Add ${feature.name}: ${item.name}`}
          </h1>
          <p className="text-sm text-muted">
            {item.kind === "button" ? "A button" : "A status tile"}. {item.description}
          </p>
        </div>
      </div>
      <Card title="Setup">
        <div className="flex flex-col gap-4">
          {!existing && siblings.length > 0 && (
            <SelectField
              label="Copy settings from"
              value=""
              onChange={(e) => {
                const source = siblings.find((s) => s.id === e.target.value);
                if (source) setValues(initialValues(fields, source.config));
              }}
              hint={`Fill in the form from another ${feature.name} you added. You can still change it.`}
            >
              <option value="">Choose one to copy</option>
              {siblings.map((sibling) => (
                <option key={sibling.id} value={sibling.id}>
                  {sibling.name}
                </option>
              ))}
            </SelectField>
          )}
          <ConfigForm fields={fields} values={values} onChange={setValues} />
          <TextField
            label="Name (optional)"
            placeholder="Named after what it adds"
            maxLength={64}
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="How this appears in the Features list. Left empty, it is named after the button or tile, such as Stop plex."
          />
          {!existing && (
            <SelectField
              label={tile ? "Put the tile on" : "Put the button on"}
              required={tile}
              value={padId}
              onChange={(e) => setPadChoice(e.target.value)}
              hint={
                tile
                  ? "A tile shows on a pad. You can move, rename or remove it later in the pad editor."
                  : "You can move, rename or remove it later in the pad editor. Without a pad, only its action is created."
              }
            >
              {pads.data?.map((pad) => (
                <option key={pad.id} value={pad.id}>
                  {pad.name}
                </option>
              ))}
              {!tile && <option value="">No pad</option>}
            </SelectField>
          )}
        </div>
      </Card>
      {existing && item.kind === "button" && <GeneratedActions instance={existing} />}
      <ErrorMessage error={create.error ?? update.error ?? remove.error} />
      <div className="flex justify-between">
        <Button type="submit" disabled={create.isPending || update.isPending}>
          {existing ? "Save" : `Add ${item.kind}`}
        </Button>
        {existing && (
          <Button
            type="button"
            variant="danger"
            onClick={confirmDelete}
            tooltip={`Delete it with the ${item.kind} it added. Run history is kept.`}
          >
            Delete
          </Button>
        )}
      </div>
    </form>
  );
}

function GeneratedActions({ instance }: { instance: FeatureInstance }) {
  const actions = useActions();
  const owned = actions.data?.filter((a) => a.feature_instance_id === instance.id) ?? [];
  return (
    <Card title="The action behind the button">
      <p className="mb-3 text-sm text-muted">
        Saving updates it in place, so its button and run history stay attached.
      </p>
      <ul className="flex flex-col gap-1 text-sm">
        {owned.map((action) => (
          <li key={action.id}>
            <Link to={`/actions/${action.id}`} className="hover:underline">
              {action.name}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
