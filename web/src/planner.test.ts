import { describe, expect, it } from "vitest";
import { defaults, FIELDS, plan } from "./planner.ts";
import { buildCurve } from "./chart.ts";
import { designEffect } from "./power.ts";

describe("evaluation plans retain assumptions and units", () => {
  it("solves the default plan and its inverse", () => {
    const p = plan("questions", defaults());
    expect(p.result.nQuestions).toBe(3053);
    expect(p.sensitivity.nQuestions).toBe(4361);
    expect(p.result.modelAnswers).toBe(6106);
    expect(p.inputs.targetDifference).toBe(0.03);
    const inverse = plan("budget", { ...defaults(), budget: p.result.nQuestions });
    expect(inverse.result.minimumDetectableEffect).toBeLessThanOrEqual(0.03);
    expect(inverse.inputs.targetDifference).toBeNull();
    expect(inverse.inputs.availableQuestions).toBe(3053);
    expect(inverse.cliCommand).toContain("--n 3053");
    expect(p.cliCommand).toContain("--delta 0.03");
    expect(p.assumptions.length).toBeGreaterThan(0);
    expect(JSON.parse(JSON.stringify(p))).toEqual(p);
  });
  it("retains exact inputs independently of slider precision", () => {
    const p = plan("questions", { ...defaults(), baseline: 65.4321, rho: 0.123456, clusterSize: 3.5, icc: 0.2 });
    expect(p.inputs.baselineAccuracy).toBe(0.654321);
    expect(p.inputs.clusterDesignEffect).toBe(1.5);
    expect(p.cliCommand).toContain("--rho 0.123456");
    expect(p.cliCommand).toContain("--cluster-deff 1.5");
  });
  it("does not coerce a gap exceeding the available accuracy range", () => {
    expect(() => plan("questions", { ...defaults(), baseline: 99, delta: 3 })).toThrow(/exceeds 100%/);
    const p = plan("budget", { ...defaults(), baseline: 99, budget: 2 });
    expect(p.result.achievableImprovement).toBe(false);
    expect(p.warnings.join(" ")).toContain("cannot detect an achievable");
  });
  it("preserves honest small-sample and group caveats", () => {
    const p = plan("budget", { ...defaults(), budget: 20, clusterSize: 10, icc: 0.2 });
    expect(p.warnings.join(" ")).toContain("Fewer than 30 questions");
    expect(p.warnings.join(" ")).toContain("Fewer than 30 groups");
    expect(p.result.approximateGroups).toBe(2);
    expect(p.result.minimumDetectableEffect).toBeGreaterThan(plan("budget", { ...defaults(), budget: 20 }).result.minimumDetectableEffect);
  });
  it("rejects every invalid active numeric input, but permits an unused draft", () => {
    for (const f of FIELDS) {
      for (const value of [NaN, Infinity, f.min - 1, f.max + 1]) {
        expect(() => plan(f.key === "budget" ? "budget" : "questions", { ...defaults(), [f.key]: value })).toThrow();
      }
    }
    expect(() => plan("budget", { ...defaults(), budget: 2.5 })).toThrow(/whole number/);
    expect(() => plan("budget", { ...defaults(), delta: NaN })).not.toThrow();
    expect(() => plan("questions", { ...defaults(), budget: NaN })).not.toThrow();
  });
  it("rejects invalid cluster designs", () => {
    for (const icc of [NaN, Infinity, -0.1, 1.1]) expect(() => designEffect(icc, 2)).toThrow();
    for (const size of [NaN, Infinity, 0]) expect(() => designEffect(0.2, size)).toThrow();
  });
  it("builds a strictly ordered, decreasing computed curve including the minimum budget", () => {
    const p = plan("budget", { ...defaults(), budget: 2 });
    const curve = buildCurve(p.inputs, 2, 20);
    expect(curve[0]!.n).toBe(2);
    expect(curve[0]!.mde).toBe(p.result.minimumDetectableEffect);
    expect(curve.at(-1)!.n).toBe(20);
    curve.slice(1).forEach((point, i) => {
      expect(point.n).toBeGreaterThan(curve[i]!.n);
      expect(point.mde).toBeLessThan(curve[i]!.mde);
    });
  });
});
