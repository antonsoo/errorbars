import { describe, expect, it } from "vitest";
import vectors from "../test-vectors.json";
import { minimumDetectableEffect, questionsNeeded } from "./power.ts";
import { invNormalCdf, zForConfidence } from "./normal.ts";

describe("questionsNeeded matches Python errorbars.power.questions_needed", () => {
  for (const vec of vectors.questionsNeeded) {
    const { baseline, delta, alpha, power, rho, samplesPerQuestion, clusterDeff } = vec.inputs;
    it(`baseline=${baseline} delta=${delta} alpha=${alpha} power=${power} rho=${rho} k=${samplesPerQuestion} deff=${clusterDeff}`, () => {
      const result = questionsNeeded(delta, {
        baselineAccuracy: baseline,
        alpha,
        power,
        rho,
        samplesPerQuestion,
        clusterDesignEffect: clusterDeff,
      });
      expect(result.nQuestions).toBe(vec.nQuestions);
      expect(result.perQuestionVariance).toBeCloseTo(vec.perQuestionVariance, 10);
    });
  }
});

describe("minimumDetectableEffect matches Python errorbars.power.minimum_detectable_effect", () => {
  for (const vec of vectors.minimumDetectableEffect) {
    const { n, baseline, alpha, power, rho, samplesPerQuestion, clusterDeff } = vec.inputs;
    it(`n=${n} baseline=${baseline} alpha=${alpha} power=${power} rho=${rho} k=${samplesPerQuestion} deff=${clusterDeff}`, () => {
      const mde = minimumDetectableEffect(n, {
        baselineAccuracy: baseline,
        alpha,
        power,
        rho,
        samplesPerQuestion,
        clusterDesignEffect: clusterDeff,
      });
      // Python side reports full float precision; a relative tolerance of
      // 1e-6 comfortably exceeds Acklam's ~1.15e-9 probit approximation
      // error compounded through the formula.
      expect(mde).toBeCloseTo(vec.mde, 6);
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
