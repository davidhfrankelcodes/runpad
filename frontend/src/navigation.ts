import { useNavigate } from "react-router";

/** Back to the page before, as the browser's Back button would; to `fallback` when this
 * page was opened directly (a link, a bookmark), so Cancel never leaves runpad. */
export function useGoBack(fallback: string): () => void {
  const navigate = useNavigate();
  return () => {
    // React Router numbers the entries it adds; 0 is where the app was opened.
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) void navigate(-1);
    else void navigate(fallback);
  };
}
