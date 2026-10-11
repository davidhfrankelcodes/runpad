import type { ReactNode } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";
import { useCurrentUser, useMe, useSetupStatus } from "./auth";
import Layout from "./components/Layout";
import { CenteredPage, ErrorMessage } from "./components/ui";
import AccountPage from "./pages/AccountPage";
import LoginPage from "./pages/LoginPage";
import PadsPage from "./pages/PadsPage";
import SecretsPage from "./pages/SecretsPage";
import SetupPage from "./pages/SetupPage";
import TargetsPage from "./pages/TargetsPage";
import UsersPage from "./pages/UsersPage";

/** Shows first-run setup or login until there is a logged-in user. */
function AuthGate() {
  const setup = useSetupStatus();
  const me = useMe();

  const error = setup.error ?? me.error;
  if (error) {
    return (
      <CenteredPage>
        <ErrorMessage error={error} />
      </CenteredPage>
    );
  }
  if (!setup.data || me.data === undefined) return null;
  if (setup.data.required) return <SetupPage />;
  if (me.data === null) return <LoginPage />;
  return <Layout />;
}

function AdminOnly({ children }: { children: ReactNode }) {
  const user = useCurrentUser();
  return user.role === "admin" ? children : <Navigate to="/" replace />;
}

const router = createBrowserRouter([
  {
    element: <AuthGate />,
    children: [
      { index: true, element: <PadsPage /> },
      { path: "account", element: <AccountPage /> },
      { path: "users", element: <AdminOnly><UsersPage /></AdminOnly> },
      { path: "targets", element: <AdminOnly><TargetsPage /></AdminOnly> },
      { path: "secrets", element: <AdminOnly><SecretsPage /></AdminOnly> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
