import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, unwrap } from "./api/client";
import { meKey, useMe } from "./auth";

/** theme.park (https://theme-park.dev) integration. runpad's colors are theme.park's CSS
 * variables, so a theme is just theme.park's stylesheet loaded after runpad's own. */

const STORAGE_KEY = "runpad.theme";
const LINK_ID = "themepark-theme";

type ThemeChoice = { url: string; theme: string | null };

export type ThemeOption = { id: string; name: string; group: "Themes" | "Community themes" };

/** Load or remove the theme stylesheet. Remembered in this browser so the login screen
 * and the next page load use it before the server answers. */
function applyTheme(choice: ThemeChoice) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(choice));
  let link = document.getElementById(LINK_ID) as HTMLLinkElement | null;
  if (!choice.theme) {
    link?.remove();
    document.documentElement.style.colorScheme = "";
    return;
  }
  const href = `${choice.url}/css/${choice.theme}.css`;
  if (link?.getAttribute("href") === href) return;
  if (!link) {
    link = document.createElement("link");
    link.id = LINK_ID;
    link.rel = "stylesheet";
    // Last in <head>, so its variables override runpad's defaults.
    document.head.appendChild(link);
  }
  link.onload = matchColorScheme;
  link.href = href;
}

/** Light themes have dark text: switch native controls (scrollbars, pickers) to match. */
function matchColorScheme() {
  const probe = document.createElement("span");
  probe.style.color = "var(--text)";
  document.body.appendChild(probe);
  const [r = 255, g = 255, b = 255] = (getComputedStyle(probe).color.match(/\d+(\.\d+)?/g) ?? []).map(Number);
  probe.remove();
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  document.documentElement.style.colorScheme = luminance < 0.5 ? "light" : "dark";
}

/** Apply the theme remembered in this browser. Call once, before rendering. */
export function restoreTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) applyTheme(JSON.parse(stored) as ThemeChoice);
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function useAppearance() {
  return useQuery({
    queryKey: ["appearance"],
    queryFn: async () => unwrap(await api.GET("/api/v1/appearance")),
    staleTime: Infinity,
  });
}

/** Keeps the page on the logged-in user's theme. Logged out, the remembered one stays. */
export function useSyncTheme() {
  const appearance = useAppearance();
  const me = useMe();
  const url = appearance.data?.themepark_url;
  const theme = me.data ? me.data.theme ?? null : undefined;
  useEffect(() => {
    if (url && theme !== undefined) applyTheme({ url, theme });
  }, [url, theme]);
}

const THEME_PATH = /\/css\/((?:community-)?theme-options\/[a-z0-9-]+)\.css/;

/** The themes theme.park publishes in its themes.json. */
export function useThemeOptions(url: string | undefined) {
  return useQuery({
    queryKey: ["themepark-themes", url],
    enabled: Boolean(url),
    staleTime: Infinity,
    queryFn: async (): Promise<ThemeOption[]> => {
      const response = await fetch(`${url}/themes.json`);
      if (!response.ok) throw new Error(`Could not load themes from ${url} (${response.status})`);
      const index = (await response.json()) as Record<string, Record<string, { url?: string }>>;
      const options: ThemeOption[] = [];
      for (const [key, group] of [
        ["themes", "Themes"],
        ["community-themes", "Community themes"],
      ] as const) {
        for (const [name, entry] of Object.entries(index[key] ?? {})) {
          const id = entry.url?.match(THEME_PATH)?.[1];
          if (id) options.push({ id, name: name.replaceAll("-", " "), group });
        }
      }
      return options.sort((a, b) => a.name.localeCompare(b.name));
    },
  });
}

export function useSetTheme() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (theme: string | null) =>
      unwrap(await api.PUT("/api/v1/auth/theme", { body: { theme } })),
    onSuccess: (user) => queryClient.setQueryData(meKey, user),
  });
}
