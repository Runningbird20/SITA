import type { MitreTechnique } from "../api/types";

/** Buckets ISO timestamps by their UTC calendar day, sorted ascending. */
export function bucketByDay(timestamps: string[]): { day: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const ts of timestamps) {
    const day = ts.slice(0, 10);
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, count]) => ({ day, count }));
}

export function groupByTactic(techniques: MitreTechnique[]): Record<string, MitreTechnique[]> {
  const grouped: Record<string, MitreTechnique[]> = {};
  for (const technique of techniques) {
    (grouped[technique.tactic] ??= []).push(technique);
  }
  return grouped;
}
