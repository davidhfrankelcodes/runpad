/** Text size that lets a label fit a pad button or tile: smaller for long labels, and for
 * long unbroken words such as container names, which cannot wrap at a space. */
export function fitText(label: string): string {
  const longestWord = Math.max(0, ...label.split(/\s+/).map((word) => word.length));
  if (label.length <= 16 && longestWord <= 12) return "text-base";
  if (label.length <= 32 && longestWord <= 18) return "text-sm";
  return "text-xs";
}

/** Labels longer than this may be cut short on a tile, so their full text gets a tooltip. */
export const LONG_LABEL = 22;
