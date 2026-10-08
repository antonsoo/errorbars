import { describe, expect, it } from "vitest";
import vectors from "../paired-vectors.json";
import { instances, repositories, repositoryIndex, submissions, unpack } from "./outcomes.ts";
import { clusterDegreesOfFreedom, mcnemarExact, pairedCompare } from "./paired.ts";
import { tCritical, tTwoSidedP } from "./tdist.ts";

/** Relative agreement, with an absolute floor for values at or near zero. */
function close(actual: number, expected: number, relative = 1e-9): void {
  expect(Math.abs(actual - expected)).toBeLessThanOrEqual(Math.max(Math.abs(expected) * relative, 1e-12));
}

describe("Student-t tails match Python errorbars.stats", () => {
  for (const { t, dof, p } of vectors.tTwoSidedP) {
    it(`P(|T| >= ${t}) on ${dof} degrees of freedom`, () => close(tTwoSidedP(t, dof), p));
  }
  for (const { confidence, dof, value } of vectors.tCritical) {
    it(`${confidence} critical value on ${dof} degrees of freedom`, () => close(tCritical(confidence, dof), value));
  }
});

describe("pairedCompare matches Python errorbars.compare.paired_compare on real submissions", () => {
  const byId = new Map(submissions.map((s) => [s.id, s]));
  for (const expected of vectors.pairs) {
    it(`${expected.a} vs ${expected.b}`, () => {
      const a = byId.get(expected.a)!;
      const b = byId.get(expected.b)!;
      const got = pairedCompare(a.resolved, b.resolved, repositoryIndex);
      expect(got.onlyA).toBe(expected.onlyA);
      expect(got.onlyB).toBe(expected.onlyB);
      expect(got.clusters).toBe(expected.clusters);
      for (const key of [
        "meanA", "meanB", "diff", "se", "ciLow", "ciHigh", "p", "mcnemarP",
        "dofClustered", "seClustered", "ciLowClustered", "ciHighClustered", "pClustered",
      ] as const) {
        close(got[key], expected[key]);
      }
      if (expected.correlation === null) expect(got.correlation).toBeNull();
      else close(got.correlation!, expected.correlation);
    });
  }
});

describe("the packed data", () => {
  it("holds 500 tasks in 12 repositories, the largest first", () => {
    expect(instances.length).toBe(500);
    expect(repositories.length).toBe(12);
    expect(repositories[0]).toBe("django/django");
    expect(repositoryIndex.filter((g) => g === 0).length).toBe(231);
  });

  it("unpacks to each submission's stated number of resolved tasks", () => {
    for (const s of submissions) {
      expect(s.resolved.length).toBe(500);
      expect(s.resolved.reduce((sum, bit) => sum + bit, 0)).toBe(Math.round(s.score * 500));
    }
  });

  it("reads bits most significant first", () => {
    expect([...unpack("a", 4)]).toEqual([1, 0, 1, 0]);
    expect([...unpack("05", 5)]).toEqual([0, 0, 1, 0, 1]);
  });

  it("leaves out the two submissions whose per-task file contradicts their score", () => {
    expect(submissions.length).toBe(173);
    expect(submissions.some((s) => s.id === "20260226_mini-v2.0.0_gemini-3-pro-high")).toBe(false);
  });
});

describe("small cases", () => {
  it("gives 3.33 degrees of freedom for SWE-bench Verified's repository sizes", () => {
    close(clusterDegreesOfFreedom([231, 75, 44, 34, 32, 22, 22, 19, 10, 8, 2, 1]), 3.330800316130594);
  });

  it("gives G - 1 degrees of freedom for equal clusters", () => {
    close(clusterDegreesOfFreedom(new Array<number>(15).fill(7)), 14);
  });

  it("runs McNemar on the discordant counts alone", () => {
    expect(mcnemarExact(0, 0)).toBe(1);
    expect(mcnemarExact(5, 5)).toBe(1);
    close(mcnemarExact(1, 9), 22 / 1024);
  });
});
