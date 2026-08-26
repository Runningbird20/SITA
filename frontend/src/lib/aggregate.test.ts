import { describe, expect, it } from "vitest";
import { bucketByDay, groupByTactic } from "./aggregate";
import type { MitreTechnique } from "../api/types";

describe("bucketByDay", () => {
  it("groups timestamps by UTC calendar day, sorted ascending", () => {
    const result = bucketByDay([
      "2026-01-15T03:00:00Z",
      "2026-01-15T10:00:00Z",
      "2026-01-14T23:00:00Z",
      "2026-01-16T00:00:00Z",
    ]);
    expect(result).toEqual([
      { day: "2026-01-14", count: 1 },
      { day: "2026-01-15", count: 2 },
      { day: "2026-01-16", count: 1 },
    ]);
  });

  it("returns an empty array for no timestamps", () => {
    expect(bucketByDay([])).toEqual([]);
  });
});

describe("groupByTactic", () => {
  const technique = (id: string, tactic: string): MitreTechnique => ({
    id,
    technique_id: id,
    name: `Technique ${id}`,
    tactic,
    description: "desc",
    dataset_version: "test",
  });

  it("groups techniques by their tactic", () => {
    const result = groupByTactic([
      technique("T1", "credential-access"),
      technique("T2", "discovery"),
      technique("T3", "credential-access"),
    ]);
    expect(Object.keys(result).sort()).toEqual(["credential-access", "discovery"]);
    expect(result["credential-access"]).toHaveLength(2);
    expect(result.discovery).toHaveLength(1);
  });

  it("returns an empty object for no techniques", () => {
    expect(groupByTactic([])).toEqual({});
  });
});
