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
  type Feature,
  type FeatureInstance,
} from "../features";
import { usePads } from "../pads";

/** Enable a feature (/features/add/:featureId) or edit an instance (/features/instances/:id). */
export default function FeatureInstancePage() {
  const { featureId, id } = useParams();
  const features = useFeatures();
  const instances = useFeatureInstances();
  const instance = id ? instances.data?.find((i) => i.id === id) : undefined;
  const feature = features.data?.find((f) => f.id === (instance?.feature_id ?? featureId));

  const error = features.error ?? instances.error;
  if (error) return <ErrorMessage error={error} />;
  if (!features.data || (id && !instances.data)) return null;
  if (id && !instance) return <ErrorMessage error={new Error("Feature instance not found")} />;
  if (!feature) return <ErrorMessage error={new Error("Unknown feature")} />;
  return <InstanceForm key={id ?? featureId} feature={feature} existing={instance} />;
}

function InstanceForm({ feature, existing }: { feature: Feature; existing?: FeatureInstance }) {
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

  function submit(event: FormEvent) {
    event.preventDefault();
    const label = name.trim() || feature.name;
    if (existing) {
      update.mutate(
        { id: existing.id, name: label, config: values },
        { onSuccess: () => void navigate("/features") },
      );
      return;
    }
    create.mutate(
      { feature_id: feature.id, name: label, config: values, pad_id: padId || null },
      { onSuccess: () => void navigate(padId ? `/pads/${padId}` : "/features") },
    );
  }

  function confirmDelete() {
    if (!existing) return;
    if (window.confirm(`Delete "${existing.name}" and the actions and buttons it created? Run history is kept.`)) {
      remove.mutate(existing.id, { onSuccess: () => void navigate("/features") });
    }
  }

  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <FeatureIcon name={feature.icon} className="h-8 w-8 text-accent" />
        <div>
          <h1 className="text-lg font-semibold">
            {existing ? `Edit ${existing.name}` : `Add ${feature.name}`}
          </h1>
          <p className="text-sm text-muted">{feature.description}</p>
        </div>
      </div>
      <Card title="Setup">
        <div className="flex flex-col gap-4">
          <TextField
            label="Name"
            placeholder={feature.name}
            maxLength={64}
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="How this appears in the Features list."
          />
          <ConfigForm fields={fields} values={values} onChange={setValues} />
          {!existing && (
            <SelectField
              label="Add to pad"
              value={padId}
              onChange={(e) => setPadChoice(e.target.value)}
              hint="Its buttons and tiles go here. You can move, rename or remove them later in the pad editor."
            >
              {pads.data?.map((pad) => (
                <option key={pad.id} value={pad.id}>
                  {pad.name}
                </option>
              ))}
              <option value="">No pad</option>
            </SelectField>
          )}
        </div>
      </Card>
      {existing && <GeneratedActions instance={existing} />}
      <ErrorMessage error={create.error ?? update.error ?? remove.error} />
      <div className="flex justify-between">
        <Button type="submit" disabled={create.isPending || update.isPending}>
          {existing ? "Save" : "Add"}
        </Button>
        {existing && (
          <Button
            type="button"
            variant="danger"
            onClick={confirmDelete}
            tooltip="Delete it with the actions, buttons, and tiles it created. Run history is kept."
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
    <Card title="Actions it created">
      <p className="mb-3 text-sm text-muted">
        Saving updates these in place, so their buttons and run history stay attached.
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
