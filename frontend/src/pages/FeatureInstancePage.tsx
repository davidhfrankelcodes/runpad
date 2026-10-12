import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useActions } from "../actions";
import { ConfigForm } from "../components/ConfigForm";
import { FeatureIcon } from "../components/FeatureIcon";
import { Button, Card, ErrorMessage, SelectField, TextField } from "../components/ui";
import {
  configFields,
  initialValues,
  useCreateInstance,
  useCreateInstances,
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
  const createMany = useCreateInstances();
  const update = useUpdateInstance();
  const remove = useDeleteInstance();
  const pads = usePads();
  const navigate = useNavigate();

  // ?from=<instance> (Clone) starts from another instance's settings.
  const fromId = useSearchParams()[0].get("from");
  const from = existing ? undefined : siblings.find((sibling) => sibling.id === fromId);
  const [name, setName] = useState(existing?.name ?? "");
  const [values, setValues] = useState(() =>
    initialValues(fields, existing?.config ?? from?.config),
  );
  // Other items of the feature to add with the same settings, by key.
  const [extras, setExtras] = useState<string[]>([]);
  const others = feature.items.filter((other) => other.key !== item.key);
  const chosen = [item, ...others.filter((other) => extras.includes(other.key))];
  const several = chosen.length > 1;
  const tile = chosen.some((c) => c.kind === "tile");
  // undefined until chosen: defaults to the first pad once pads have loaded. A tile needs a
  // pad, so "No pad" falls back to the first one when a tile is chosen.
  const [padChoice, setPadChoice] = useState<string>();
  const firstPad = pads.data?.[0]?.id ?? "";
  const padId = padChoice === "" && tile ? firstPad : (padChoice ?? firstPad);

  function toggleExtra(key: string, on: boolean) {
    setExtras((current) => (on ? [...current, key] : current.filter((k) => k !== key)));
  }

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
    const done = { onSuccess: () => void navigate(padId ? `/pads/${padId}` : "/features") };
    if (several) {
      createMany.mutate(
        {
          feature_id: feature.id,
          items: chosen.map((c) => c.key),
          config: values,
          pad_id: padId || null,
        },
        done,
      );
      return;
    }
    create.mutate(
      { feature_id: feature.id, item: item.key, name: label, config: values, pad_id: padId || null },
      done,
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
          {!existing && others.length > 0 && (
            <fieldset className="flex flex-col gap-2 text-sm">
              <legend className="mb-1 text-soft">Also add, with the same settings</legend>
              {others.map((other) => (
                <label key={other.key} className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={extras.includes(other.key)}
                    onChange={(e) => toggleExtra(other.key, e.target.checked)}
                  />
                  <span>
                    {other.name} <span className="text-faint">({other.kind})</span>
                    <span className="block text-xs text-faint">{other.description}</span>
                  </span>
                </label>
              ))}
              <span className="text-xs text-faint">
                Each becomes its own button or tile, which you can edit or delete on its own.
              </span>
            </fieldset>
          )}
          <TextField
            label="Name (optional)"
            placeholder="Named after what it adds"
            maxLength={64}
            value={several ? "" : name}
            disabled={several}
            onChange={(e) => setName(e.target.value)}
            hint={
              several
                ? "Adding several: each is named after what it adds, such as Stop plex."
                : "How this appears in the Features list. Left empty, it is named after the button or tile, such as Stop plex."
            }
          />
          {!existing && (
            <SelectField
              label={several ? "Put them on" : tile ? "Put the tile on" : "Put the button on"}
              required={tile}
              value={padId}
              onChange={(e) => setPadChoice(e.target.value)}
              hint={
                tile
                  ? "Tiles show on a pad. You can move, rename or remove them later in the pad editor."
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
      <ErrorMessage error={create.error ?? createMany.error ?? update.error ?? remove.error} />
      <div className="flex justify-between">
        <Button
          type="submit"
          disabled={create.isPending || createMany.isPending || update.isPending}
        >
          {existing ? "Save" : several ? `Add ${chosen.length}` : `Add ${item.kind}`}
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
