import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { runsKey } from "./actions";
import { api, unwrap, type Schemas } from "./api/client";

export type AppSettings = Schemas["AppSettingsRead"];
export type RetentionDays = AppSettings["run_retention_days"];

const settingsKey = ["settings"] as const;

export const RETENTION_CHOICES: { label: string; days: RetentionDays }[] = [
  { label: "7 days", days: 7 },
  { label: "14 days", days: 14 },
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "180 days", days: 180 },
  { label: "1 year", days: 365 },
  { label: "Forever", days: null },
];

export function useAppSettings() {
  return useQuery({
    queryKey: settingsKey,
    queryFn: async () => unwrap(await api.GET("/api/v1/settings")),
  });
}

export function useUpdateAppSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: AppSettings) => unwrap(await api.PUT("/api/v1/settings", { body })),
    onSuccess: (settings) => {
      queryClient.setQueryData(settingsKey, settings);
      // Shortening retention deletes old runs right away.
      void queryClient.invalidateQueries({ queryKey: runsKey });
    },
  });
}
