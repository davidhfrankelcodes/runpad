import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import { isUnauthorized, meKey } from "./auth";
import "./index.css";
import { restoreTheme } from "./theme";

const queryClient = new QueryClient({
  // An expired or revoked session anywhere sends the user back to the login screen.
  queryCache: new QueryCache({
    onError: (error) => {
      if (isUnauthorized(error)) queryClient.setQueryData(meKey, null);
    },
  }),
  defaultOptions: {
    queries: { retry: (count, error) => !isUnauthorized(error) && count < 2 },
  },
});

restoreTheme();

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
