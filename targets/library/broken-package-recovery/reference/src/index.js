import { formatSummary } from "./utils/formatter.js";

export function summarize(items) {
  const clean = items.map((x) => String(x).trim()).filter(Boolean);
  return formatSummary(clean);
}
