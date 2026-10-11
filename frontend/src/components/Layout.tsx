import { NavLink, Outlet } from "react-router";
import { useCurrentUser, useLogout } from "../auth";

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"}`;
}

export default function Layout() {
  const user = useCurrentUser();
  const logout = useLogout();

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col p-6">
      <header className="flex items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div className="flex items-center gap-6">
          <span className="text-xl font-semibold tracking-tight">runpad</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={navClass}>
              Pads
            </NavLink>
            {user.role === "admin" && (
              <NavLink to="/users" className={navClass}>
                Users
              </NavLink>
            )}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <NavLink to="/account" className={navClass}>
            {user.username}
          </NavLink>
          <button
            type="button"
            className="text-zinc-400 hover:text-white"
            onClick={() => logout.mutate()}
          >
            Log out
          </button>
        </div>
      </header>
      <main className="flex flex-1 flex-col py-6">
        <Outlet />
      </main>
    </div>
  );
}
