import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { actionsKey } from "./actions";
import { api, unwrap, type Schemas } from "./api/client";
import { padsKey } from "./pads";

export type Feature = Schemas["FeatureRead"];
export type FeatureInstance = Schemas["FeatureInstanceRead"];
export type ConfigValue = string | number | boolean;
export type ConfigValues = Record<string, ConfigValue>;

/** The parts of a JSON schema property the setup form understands. Features are
 * in-repo code, so their config models stay within these. */
export interface ConfigField {
  name: string;
  type: "string" | "integer" | "number" | "boolean";
  title: string;
  description?: string;
  required: boolean;
  pattern?: string;
  maxLength?: number;
  minimum?: number;
  maximum?: number;
  choices?: string[];
  default?: ConfigValue;
  targetKind?: "ssh" | "http";
  multiline: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

/** The form fields of a feature's config schema, in declaration order. */
export function configFields(feature: Feature): ConfigField[] {
  const schema = feature.config_schema;
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const required = Array.isArray(schema.required) ? schema.required : [];
  return Object.entries(properties).flatMap(([name, prop]): ConfigField[] => {
    if (!isRecord(prop)) return [];
    const choices = Array.isArray(prop.enum) ? prop.enum.filter((c) => typeof c === "string") : undefined;
    const targetKind = prop["x-target-kind"];
    const type = choices ? "string" : str(prop.type);
    if (type !== "string" && type !== "integer" && type !== "number" && type !== "boolean") {
      return [];
    }
    const fallback = prop.default;
    return [
      {
        name,
        type,
        title: str(prop.title) ?? name,
        description: str(prop.description),
        required: required.includes(name),
        pattern: str(prop.pattern),
        maxLength: num(prop.maxLength),
        minimum: num(prop.minimum),
        maximum: num(prop.maximum),
        choices,
        default:
          typeof fallback === "string" || typeof fallback === "number" || typeof fallback === "boolean"
            ? fallback
            : undefined,
        targetKind: targetKind === "ssh" || targetKind === "http" ? targetKind : undefined,
        multiline: prop["x-multiline"] === true,
      },
    ];
  });
}

export function initialValues(fields: ConfigField[], config?: Record<string, unknown>): ConfigValues {
  const values: ConfigValues = {};
  for (const field of fields) {
    const current = config?.[field.name];
    if (typeof current === "string" || typeof current === "number" || typeof current === "boolean") {
      values[field.name] = current;
    } else if (field.default !== undefined) {
      values[field.name] = field.default;
    } else if (field.type === "boolean") {
      values[field.name] = false;
    }
  }
  return values;
}

const featuresKey = ["features"] as const;
const instancesKey = ["feature-instances"] as const;

export function useFeatures() {
  return useQuery({
    queryKey: featuresKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/features")),
    staleTime: Infinity, // The catalog is code; it only changes with a new release.
  });
}

export function useFeatureInstances() {
  return useQuery({
    queryKey: instancesKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/feature-instances")),
  });
}

/** Instances own Actions and Buttons, so every change refreshes those too. */
function useInvalidateInstances() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      [instancesKey, actionsKey, padsKey].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    );
}

export function useCreateInstance() {
  const onSuccess = useInvalidateInstances();
  return useMutation({
    mutationFn: async (body: Schemas["FeatureInstanceCreate"]) =>
      unwrap(await api.POST("/api/v1/feature-instances", { body })),
    onSuccess,
  });
}

export function useUpdateInstance() {
  const onSuccess = useInvalidateInstances();
  return useMutation({
    mutationFn: async ({ id, ...body }: Schemas["FeatureInstanceUpdate"] & { id: string }) =>
      unwrap(
        await api.PATCH("/api/v1/feature-instances/{instance_id}", {
          params: { path: { instance_id: id } },
          body,
        }),
      ),
    onSuccess,
  });
}

export function useDeleteInstance() {
  const onSuccess = useInvalidateInstances();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await api.DELETE("/api/v1/feature-instances/{instance_id}", {
          params: { path: { instance_id: id } },
        }),
      ),
    onSuccess,
  });
}
