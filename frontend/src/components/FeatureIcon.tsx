/** Icons for catalog features, by the `icon` name in each feature's manifest. */
const PATHS: Record<string, string> = {
  // A shipping container.
  container:
    "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9ZM3 7.5 12 12m0 0 9-4.5M12 12v9M7.5 5.25l9 4.5",
  // Stacked layers.
  stack: "M12 3 3 7.5l9 4.5 9-4.5L12 3ZM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5",
  // A gear.
  service:
    "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M4.9 19.1 7 17m10-10 2.1-2.1",
  // A power symbol.
  power: "M12 3v8M7.05 6.05a7 7 0 1 0 9.9 0",
  // A sunrise.
  wake: "M3 18h18M6 18a6 6 0 0 1 12 0M12 4v4M4.9 9.9l1.4 1.4m11.4 0 1.4-1.4",
  // A paper plane.
  webhook: "M21 3 3 10.5l7 2.5 2.5 7L21 3ZM10 13l4-4",
  // A pulse line.
  ping: "M3 12h4l2-5 4 10 2-5h6",
  // A globe.
  website: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9Z",
  // A plug.
  port: "M9 3v5m6-5v5M6 8h12v3a6 6 0 0 1-12 0V8Zm6 9v4",
  // A padlock.
  certificate: "M6 11h12v10H6V11Zm2.5 0V7.5a3.5 3.5 0 0 1 7 0V11M12 15v2",
  // A gauge.
  gauge: "M4.2 17a9 9 0 1 1 15.6 0M12 13l4-4M12 13a1 1 0 1 0 0 .01",
  // A box with a down arrow: package updates.
  updates: "M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9ZM12 8v7m-3-3 3 3 3-3",
  // A rack server.
  server: "M4 4h16v6H4V4Zm0 10h16v6H4v-6Zm3-7h.01M7 17h.01",
  // A monitor.
  monitor: "M3 4h18v12H3V4Zm6 16h6m-3-4v4",
  // A database cylinder: storage pools.
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 0v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  // A house.
  home: "M3 11 12 3l9 8M5 9.5V21h5v-6h4v6h5V9.5",
  // A pipeline: stages joined left to right, for a CI job.
  jenkins:
    "M3 12a2 2 0 1 0 4 0 2 2 0 1 0-4 0Zm7 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0Zm7 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0ZM7 12h3m4 0h3",
  // A cog on a box: a build agent.
  agent: "M4 14h16v6H4v-6Zm3 3h.01M12 3v2m0 6v-2m-3-1H7m10 0h-2m-5.1-2.9L8.5 3.7m7 0-1.4 1.4M12 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  // A clock with an arrow running back around it: a backup.
  backup: "M3 12a9 9 0 1 0 2.6-6.4M3 4v5h5M12 8v4l3 2",
  // A shell prompt: custom commands.
  terminal: "M4 4h16v16H4zM8 9l3 3-3 3M13 15h3",
  // A puzzle piece: a feature this version no longer has.
  feature: "M10 4a2 2 0 1 1 4 0v2h4v4h-2a2 2 0 1 0 0 4h2v4h-4v-2a2 2 0 1 0-4 0v2H6v-4h2a2 2 0 1 0 0-4H6V6h4z",
};

const FALLBACK = "M4 4h16v16H4z";

export function FeatureIcon({ name, className = "h-6 w-6" }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d={PATHS[name] ?? FALLBACK} />
    </svg>
  );
}
