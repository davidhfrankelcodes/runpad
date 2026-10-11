/** Icons for catalog features, by the `icon` name in each feature's manifest. */
const PATHS: Record<string, string> = {
  // A shipping container.
  container:
    "M3 7.5 12 3l9 4.5v9L12 21l-9-4.5v-9ZM3 7.5 12 12m0 0 9-4.5M12 12v9M7.5 5.25l9 4.5",
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
