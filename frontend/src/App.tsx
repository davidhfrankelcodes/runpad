import type { ReactNode } from "react";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router";
import { useCurrentUser, useMe, useSetupStatus } from "./auth";
import { useSyncTheme } from "./theme";
import Layout from "./components/Layout";
import { CenteredPage, ErrorMessage } from "./components/ui";
import AccountPage from "./pages/AccountPage";
import ActionEditorPage from "./pages/ActionEditorPage";
import ActionsPage from "./pages/ActionsPage";
import FeatureInstancePage from "./pages/FeatureInstancePage";
import FeaturesPage from "./pages/FeaturesPage";
import LoginPage from "./pages/LoginPage";
import PadPage from "./pages/PadPage";
import PadsPage from "./pages/PadsPage";
import RunPage from "./pages/RunPage";
import RunsPage from "./pages/RunsPage";
import SecretsPage from "./pages/SecretsPage";
import SetupPage from "./pages/SetupPage";
import TargetsPage from "./pages/TargetsPage";
import UsersPage from "./pages/UsersPage";

/** Shows first-run setup or login until there is a logged-in user. */
function AuthGate() {
  const setup = useSetupStatus();
  const me = useMe();
  useSyncTheme();

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
      { path: "pads/:id", element: <PadPage /> },
      { path: "account", element: <AccountPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "runs/:id", element: <RunPage /> },
      { path: "actions", element: <AdminOnly><ActionsPage /></AdminOnly> },
      { path: "actions/new", element: <AdminOnly><ActionEditorPage /></AdminOnly> },
      { path: "actions/:id", element: <AdminOnly><ActionEditorPage /></AdminOnly> },
      { path: "features", element: <AdminOnly><FeaturesPage /></AdminOnly> },
      { path: "features/add/:featureId", element: <AdminOnly><FeatureInstancePage /></AdminOnly> },
      { path: "features/instances/:id", element: <AdminOnly><FeatureInstancePage /></AdminOnly> },
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
