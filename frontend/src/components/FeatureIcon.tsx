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
