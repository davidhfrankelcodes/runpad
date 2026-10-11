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
    document.documentElement.style.removeProperty("--runpad-option-bg");
    setThemeColor(DEFAULT_THEME_COLOR);
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

type Rgb = [number, number, number];

/** A CSS color as RGB, through the browser's own parsing, or null if it is not a color. */
function toRgb(color: string): Rgb | null {
  const probe = document.createElement("span");
  probe.style.color = color;
  if (!probe.style.color) return null;
  document.body.appendChild(probe);
  const parts = (getComputedStyle(probe).color.match(/\d+(\.\d+)?/g) ?? []).map(Number);
  probe.remove();
  const [r = 0, g = 0, b = 0, alpha = 1] = parts;
  return alpha < 1 ? null : [r, g, b]; // Only opaque colors can be a solid list background.
}

function luminance([r, g, b]: Rgb): number {
  const linear = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

/** Match native controls to the theme: light themes have dark text, so scrollbars and
 * pickers switch to light. And give <select> lists a solid background that reads well
 * with the text, since browsers cannot paint the theme's gradients there. */
function matchColorScheme() {
  const root = document.documentElement;
  const css = getComputedStyle(root);
  const text = toRgb("var(--text)") ?? [255, 255, 255];
  const lightText = luminance(text) > 0.18;
  root.style.colorScheme = lightText ? "dark" : "light";
  const dropdown = css.getPropertyValue("--drop-down-menu-bg").trim();
  const solid = toRgb(dropdown);
  root.style.setProperty(
    "--runpad-option-bg",
    solid && contrast(solid, text) >= 4.5 ? dropdown : lightText ? "#18181b" : "#ffffff",
  );
  // The phone's browser bar follows the theme: the first color of its background.
  const background = getComputedStyle(document.documentElement).getPropertyValue("--main-bg-color");
  const color = background.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)/i)?.[0];
  if (color) setThemeColor(color);
}

const DEFAULT_THEME_COLOR = "#09090b";

function setThemeColor(color: string) {
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", color);
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
