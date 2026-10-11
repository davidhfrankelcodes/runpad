import { NavLink, Outlet, useLocation } from "react-router";
import { useCurrentUser, useLogout } from "../auth";
import { useLiveEvents } from "../events";
import { Tooltip } from "./ui";

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-raised text-fg-hover" : "text-muted hover:text-fg-hover"}`;
}

export default function Layout() {
  const user = useCurrentUser();
  const logout = useLogout();
  const location = useLocation();
  useLiveEvents();

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col p-6">
      <header className="flex items-center justify-between gap-4 border-b border-line pb-4">
        <div className="flex items-center gap-6">
          <span className="text-xl font-semibold tracking-tight">runpad</span>
          <nav className="flex gap-1">
            <Tooltip side="bottom" text="Pages of buttons and status tiles.">
            <NavLink
              to="/"
              className={({ isActive }) =>
                navClass({ isActive: isActive || location.pathname.startsWith("/pads/") })
              }
            >
              Pads
            </NavLink>
            </Tooltip>
<Tooltip
              side="bottom"
              text={
                user.role === "admin"
                  ? "Every run: who pressed what, when, and its output."
                  : "Runs you started, with their output."
              }
            >
            <NavLink to="/runs" className={navClass}>
              Runs
            </NavLink>
            </Tooltip>
            {user.role === "admin" && (
              <>
                <Tooltip side="bottom" text="Ready-made buttons and status tiles for Docker, systemd, power, and more.">
                <NavLink to="/features" className={navClass}>
                  Features
                </NavLink>
                </Tooltip>
                <Tooltip side="bottom" text="The commands buttons run: custom ones, and those features created.">
                <NavLink to="/actions" className={navClass}>
                  Actions
                </NavLink>
                </Tooltip>
                <Tooltip side="bottom" text="SSH hosts and HTTP endpoints that actions run on.">
                <NavLink to="/targets" className={navClass}>
                  Targets
                </NavLink>
                </Tooltip>
                <Tooltip side="bottom" text="SSH keys and tokens, stored encrypted and never shown again.">
                <NavLink to="/secrets" className={navClass}>
                  Secrets
                </NavLink>
                </Tooltip>
                <Tooltip side="bottom" text="Who can log in, their role, and their password.">
                <NavLink to="/users" className={navClass}>
                  Users
                </NavLink>
                </Tooltip>
              </>
            )}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Tooltip side="bottom" text="Your account: password and theme.">
          <NavLink to="/account" className={navClass}>
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
      </header>
      <main className="flex flex-1 flex-col py-6">
        <Outlet />
      </main>
    </div>
  );
}
