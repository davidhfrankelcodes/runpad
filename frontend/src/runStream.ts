import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { runsKey, type RunDetail } from "./actions";

/** Follow a Run's output over Server-Sent Events. The server replays output from the
 * start on every connection, so a reconnect resets what has been collected. */
export function useRunStream(runId: string) {
  const queryClient = useQueryClient();
  const [output, setOutput] = useState("");
  const [end, setEnd] = useState<RunDetail | null>(null);

  useEffect(() => {
    const source = new EventSource(`/api/v1/runs/${runId}/stream`);
    source.onopen = () => setOutput("");
    source.addEventListener("output", (event) => {
      const chunk = JSON.parse((event as MessageEvent<string>).data) as string;
      setOutput((current) => current + chunk);
    });
    source.addEventListener("end", (event) => {
      const run = JSON.parse((event as MessageEvent<string>).data) as RunDetail;
      setEnd(run);
      source.close();
      queryClient.setQueryData([...runsKey, runId], run);
      void queryClient.invalidateQueries({ queryKey: [...runsKey, "list"] });
    });
    return () => source.close();
  }, [runId, queryClient]);

  return { output, end };
}
