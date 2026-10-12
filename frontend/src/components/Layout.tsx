import { useId, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useCurrentUser, useLogout } from "../auth";
import { useLiveEvents } from "../events";
import type { User } from "../api/client";
import { Tooltip } from "./ui";

type NavItem = { to: string; label: string; tip: string; adminOnly?: boolean };

function navItems(user: User): NavItem[] {
  return [
    { to: "/", label: "Pads", tip: "Pages of buttons and status tiles." },
    {
      to: "/runs",
      label: "Runs",
      tip:
        user.role === "admin"
          ? "Every run: who pressed what, when, and its output."
          : "Runs you started, with their output.",
    },
    {
      to: "/features",
      label: "Features",
      tip: "Ready-made buttons and status tiles for Docker, systemd, power, and more.",
      adminOnly: true,
    },
    {
      to: "/actions",
      label: "Actions",
      tip: "The commands buttons run: custom ones, and those features created.",
      adminOnly: true,
    },
    {
      to: "/tiles",
      label: "Tiles",
      tip: "Status tiles: what each one checks, its state now, and the pads it is on.",
      adminOnly: true,
    },
    {
      to: "/targets",
      label: "Targets",
      tip: "SSH hosts and HTTP endpoints that actions run on.",
      adminOnly: true,
    },
    {
      to: "/secrets",
      label: "Secrets",
      tip: "SSH keys and tokens, stored encrypted and never shown again.",
      adminOnly: true,
    },
    {
      to: "/users",
      label: "Users",
      tip: "Who can log in, their role, and their password.",
      adminOnly: true,
    },
  ].filter((item) => !item.adminOnly || user.role === "admin");
}

const API_DOCS = "/api/v1/docs";
const API_TIP =
  "Interactive API docs (Swagger), in a new tab. Authorize with a token from your Account page.";

/** A label with an arrow out of a box: opens in a new tab. */
function ExternalLabel({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {children}
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className="h-3.5 w-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
      </svg>
    </span>
  );
}

function linkClass(isActive: boolean) {
  return `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-raised text-fg-hover" : "text-muted hover:text-fg-hover"}`;
}

export default function Layout() {
  const user = useCurrentUser();
  const logout = useLogout();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();
  useLiveEvents();

  const items = navItems(user);
  const active = (item: NavItem) =>
    item.to === "/"
      ? location.pathname === "/" || location.pathname.startsWith("/pads/")
      : location.pathname.startsWith(item.to);

  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-4 sm:p-6">
      <header className="border-b border-line pb-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <Tooltip side="bottom" text="Home: your first pad.">
              <Link
                to="/"
                className="flex items-center gap-2 text-xl font-semibold tracking-tight hover:text-fg-hover"
                onClick={() => setMenuOpen(false)}
              >
                <img src="/favicon.svg" alt="" className="h-7 w-7" />
                runpad
              </Link>
            </Tooltip>
            {/* Wide screens: the full navigation in one row. */}
            <nav aria-label="Main" className="hidden gap-1 md:flex">
              {items.map((item) => (
                <Tooltip key={item.to} side="bottom" text={item.tip}>
                  <NavLink to={item.to} className={() => linkClass(active(item))}>
                    {item.label}
                  </NavLink>
                </Tooltip>
              ))}
              <Tooltip side="bottom" text={API_TIP}>
                <a href={API_DOCS} target="_blank" rel="noreferrer" className={linkClass(false)}>
                  <ExternalLabel>API</ExternalLabel>
                </a>
              </Tooltip>
            </nav>
          </div>
          <div className="hidden items-center gap-3 text-sm md:flex">
            <Tooltip side="bottom" text="Your account: password and theme.">
              <NavLink to="/account" className={({ isActive }) => linkClass(isActive)}>
                {user.username}
              </NavLink>
            </Tooltip>
            <Tooltip side="bottom" text="End your session in this browser.">
              <button
                type="button"
                className="text-muted hover:text-fg-hover"
                onClick={() => logout.mutate()}
              >
                Log out
              </button>
            </Tooltip>
          </div>
          {/* Phones: a menu button. */}
          <button
            type="button"
            className="rounded-md bg-raised px-3 py-2 text-sm md:hidden"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? "Close" : "Menu"}
          </button>
        </div>
        {menuOpen && (
          <nav id={menuId} aria-label="Main" className="mt-3 flex flex-col gap-1 md:hidden">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={() => `${linkClass(active(item))} py-2.5 text-base`}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
                <span className="block text-xs text-faint">{item.tip}</span>
              </NavLink>
            ))}
            <a
              href={API_DOCS}
              target="_blank"
              rel="noreferrer"
              className={`${linkClass(false)} py-2.5 text-base`}
              onClick={() => setMenuOpen(false)}
            >
              <ExternalLabel>API</ExternalLabel>
              <span className="block text-xs text-faint">{API_TIP}</span>
            </a>
            <div className="mt-2 flex items-center justify-between border-t border-line pt-3">
              <NavLink
                to="/account"
                className={({ isActive }) => `${linkClass(isActive)} py-2.5 text-base`}
                onClick={() => setMenuOpen(false)}
              >
                {user.username}
                <span className="block text-xs text-faint">Password and theme.</span>
              </NavLink>
              <button
                type="button"
                className="rounded-md px-3 py-2.5 text-base text-muted hover:text-fg-hover"
                onClick={() => logout.mutate()}
              >
                Log out
              </button>
            </div>
          </nav>
        )}
      </header>
      <main className="flex flex-1 flex-col py-6">
        <Outlet />
      </main>
    </div>
  );
}
