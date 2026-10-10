import { describe, expect, it } from "vitest";
import vectors from "../test-vectors.json";
import { minimumDetectableEffect, perQuestionVariance, questionsNeeded } from "./power.ts";
import { invNormalCdf, zForConfidence } from "./normal.ts";

describe("repeated answers preserve question difficulty", () => {
  it("matches the uniform-difficulty example's independent variance components", () => {
    for (const k of [1, 2, 4, 6, 100]) {
      expect(perQuestionVariance({ baselineAccuracy: 0.5, samplesPerQuestion: k, repeatCorrelation: 1 / 3 }))
        .toBeCloseTo(1 / 12 + 1 / (6 * k), 14);
    }
  });
  it("refuses to infer independence when repeat dependence was not supplied", () => {
    const inputs = { baselineAccuracy: 0.5, samplesPerQuestion: 100 };
    expect(() => questionsNeeded(0.05, inputs)).toThrow(/repeatCorrelation is required/);
    expect(() => minimumDetectableEffect(500, inputs)).toThrow(/repeatCorrelation is required/);
    expect(questionsNeeded(0.05, { baselineAccuracy: 0.5 }).repeatCorrelation).toBeNull();
  });
  it("identical repeats give no budget reduction", () => {
    for (const k of [2, 10, 100, Number.MAX_SAFE_INTEGER]) {
      expect(questionsNeeded(0.05, { baselineAccuracy: 0.5, samplesPerQuestion: k, repeatCorrelation: 1 }).nQuestions)
        .toBe(1570);
    }
  });
  it("keeps independent repeats as an explicit choice", () => {
    const inputs = { baselineAccuracy: 0.5, samplesPerQuestion: 100 };
    expect(questionsNeeded(0.05, { ...inputs, repeatCorrelation: 0 }).nQuestions).toBe(16);
    expect(questionsNeeded(0.05, { ...inputs, repeatCorrelation: 0.8 }).nQuestions).toBe(1259);
  });
  it("validates the repeat assumption even with one answer", () => {
    for (const r of [-0.1, 1.1, NaN, Infinity]) {
      for (const k of [1, 4]) {
        const inputs = { baselineAccuracy: 0.5, samplesPerQuestion: k, repeatCorrelation: r };
        expect(() => questionsNeeded(0.05, inputs)).toThrow(/repeatCorrelation must be/);
        expect(() => minimumDetectableEffect(500, inputs)).toThrow(/repeatCorrelation must be/);
      }
    }
  });
});

describe("questionsNeeded matches Python errorbars.power.questions_needed", () => {
  for (const vec of vectors.questionsNeeded) {
    const { baseline, delta, alpha, power, rho, samplesPerQuestion, repeatCorrelation, clusterDeff } = vec.inputs;
    it(`baseline=${baseline} delta=${delta} alpha=${alpha} power=${power} rho=${rho} k=${samplesPerQuestion} deff=${clusterDeff}`, () => {
      const result = questionsNeeded(delta, {
        baselineAccuracy: baseline,
        alpha,
        power,
        rho,
        samplesPerQuestion,
        ...(repeatCorrelation === null ? {} : { repeatCorrelation }),
        clusterDesignEffect: clusterDeff,
      });
      expect(result.nQuestions).toBe(vec.nQuestions);
      expect(result.perQuestionVariance).toBeCloseTo(vec.perQuestionVariance, 10);
      expect(result.repeatCorrelation).toBe(repeatCorrelation);
    });
  }
});

describe("minimumDetectableEffect matches Python errorbars.power.minimum_detectable_effect", () => {
  for (const vec of vectors.minimumDetectableEffect) {
    const { n, baseline, alpha, power, rho, samplesPerQuestion, repeatCorrelation, clusterDeff } = vec.inputs;
    it(`n=${n} baseline=${baseline} alpha=${alpha} power=${power} rho=${rho} k=${samplesPerQuestion} deff=${clusterDeff}`, () => {
      const mde = minimumDetectableEffect(n, {
        baselineAccuracy: baseline,
        alpha,
        power,
        rho,
        samplesPerQuestion,
        ...(repeatCorrelation === null ? {} : { repeatCorrelation }),
        clusterDesignEffect: clusterDeff,
      });
      // Formula outputs agree within floating-point arithmetic noise.
      expect(Math.abs(mde - vec.mde)).toBeLessThanOrEqual(Math.abs(vec.mde) * 1e-14);
    });
  }
});

describe("invNormalCdf / zForConfidence sanity checks", () => {
  it("matches well-known quantiles", () => {
    expect(invNormalCdf(0.5)).toBeCloseTo(0, 9);
    expect(zForConfidence(0.95)).toBeCloseTo(1.959963985, 8);
    expect(zForConfidence(0.9)).toBeCloseTo(1.644853627, 8);
    expect(zForConfidence(0.99)).toBeCloseTo(2.575829304, 8);
  });

  it("throws outside (0, 1)", () => {
    expect(() => invNormalCdf(0)).toThrow();
    expect(() => invNormalCdf(1)).toThrow();
    expect(() => invNormalCdf(-0.1)).toThrow();
  });
});

describe("input validation matches the Python package", () => {
  it("rejects a baseline at or outside 0 and 1", () => {
    for (const baselineAccuracy of [0, 1, -0.1, 1.2]) {
      expect(() => questionsNeeded(0.05, { baselineAccuracy })).toThrow(/strictly between 0 and 1/);
    }
  });

  it("rejects a target accuracy above 1", () => {
    expect(() => questionsNeeded(0.05, { baselineAccuracy: 0.98 })).toThrow(/can't exceed 1/);
  });

  it("rejects a non-positive variance", () => {
    expect(() => questionsNeeded(0.05, { variance: 0 })).toThrow(/variance must be positive/);
  });
});

describe("both directions enforce the same finite planning domain", () => {
  for (const inputs of [
    { baselineAccuracy: 0.5, rho: NaN },
    { baselineAccuracy: 0.5, rho: 2 },
    { baselineAccuracy: 0.5, clusterDesignEffect: 0.1 },
    { baselineAccuracy: 0.5, clusterDesignEffect: Infinity },
    { baselineAccuracy: 0.5, alpha: NaN },
    { baselineAccuracy: 0.5, power: NaN },
    { baselineAccuracy: 0.5, power: 0.001 },
    { baselineAccuracy: 0.5, samplesPerQuestion: Infinity },
    { baselineAccuracy: 0.5, samplesPerQuestion: 1.5 },
    { variance: Infinity },
    { variance: NaN },
  ]) {
    it(`rejects ${JSON.stringify(inputs)}`, () => {
      expect(() => questionsNeeded(0.03, inputs)).toThrow();
      expect(() => minimumDetectableEffect(500, inputs)).toThrow();
    });
  }
  it("rejects NaN and infinite deltas and noninteger budgets", () => {
    for (const delta of [NaN, Infinity, -Infinity, 1e-200]) {
      expect(() => questionsNeeded(delta, { baselineAccuracy: 0.5 })).toThrow();
    }
    for (const n of [NaN, Infinity, 2.5, 2 ** 53, 1]) {
      expect(() => minimumDetectableEffect(n, { baselineAccuracy: 0.5 })).toThrow();
    }
  });
  it("rejects NaN quantiles", () => {
    expect(() => invNormalCdf(NaN)).toThrow();
    expect(() => zForConfidence(NaN)).toThrow();
  });
  it("preserves representable extreme calculations", () => {
    expect(minimumDetectableEffect(500, { baselineAccuracy: 0.5, alpha: 1e-30 })).toBeGreaterThan(0.3);
    expect(Number.isFinite(minimumDetectableEffect(100, { variance: 1e308 }))).toBe(true);
  });
});


describe("AS241 agrees with independent SciPy ndtri quantiles", () => {
  for (const { p, z } of vectors.normalQuantiles) {
    it(`p=${p}`, () => {
      expect(Math.abs(invNormalCdf(p) - z)).toBeLessThanOrEqual(Math.max(1, Math.abs(z)) * 1e-14);
    });
  }
});
