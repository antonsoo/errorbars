/**
 * Statistical power formulas for paired LLM eval comparisons.
 *
 * This is a line-for-line port of `src/errorbars/power.py` in the Python
 * package — same variable names, same derivation, same defaults — kept in
 * sync by comparing against Python-generated vectors in
 * `src/power.test.ts`. See `docs/formulas.md` §11 in the main repo for the
 * derivation and the modeling caveats.
 */

import { invNormalCdf, zForConfidence } from "./normal.ts";

export interface VarianceInputs {
  /** Binary metric: baseline accuracy p, giving per-sample variance p(1-p). */
  baselineAccuracy?: number;
  /** Continuous metric: raw per-sample variance. */
  variance?: number;
  samplesPerQuestion?: number;
}

export function perQuestionVariance({
  baselineAccuracy,
  variance,
  samplesPerQuestion = 1,
}: VarianceInputs): number {
  if ((baselineAccuracy !== undefined) === (variance !== undefined)) {
    throw new Error("pass exactly one of baselineAccuracy or variance");
  }
  if (samplesPerQuestion < 1) {
    throw new Error("samplesPerQuestion must be >= 1");
  }
  const v =
    baselineAccuracy !== undefined ? baselineAccuracy * (1 - baselineAccuracy) : (variance as number);
  return v / samplesPerQuestion;
}

function zBeta(power: number): number {
  if (power <= 0 || power >= 1) {
    throw new Error(`power must be in (0, 1), got ${power}`);
  }
  return invNormalCdf(power);
}

export interface PowerInputs extends VarianceInputs {
  alpha?: number;
  power?: number;
  rho?: number;
  clusterDesignEffect?: number;
}

export interface PowerResult {
  nQuestions: number;
  delta: number;
  alpha: number;
  power: number;
  rho: number;
  samplesPerQuestion: number;
  clusterDesignEffect: number;
  perQuestionVariance: number;
}

/**
 * Number of questions needed to detect a paired mean difference `delta`.
 *
 * n = (z_{a/2} + z_b)^2 * 2*V*(1-rho) * deff / delta^2
 */
export function questionsNeeded(delta: number, inputs: PowerInputs): PowerResult {
  const {
    alpha = 0.05,
    power = 0.8,
    rho = 0,
    samplesPerQuestion = 1,
    clusterDesignEffect = 1,
  } = inputs;
  if (delta <= 0) throw new Error("delta must be positive");
  if (rho < -1 || rho > 1) throw new Error("rho must be in [-1, 1]");
  if (clusterDesignEffect < 1) throw new Error("clusterDesignEffect must be >= 1");

  const v = perQuestionVariance({ ...inputs, samplesPerQuestion });
  const zA = zForConfidence(1 - alpha);
  const zB = zBeta(power);
  const n = ((zA + zB) ** 2 * 2 * v * (1 - rho) * clusterDesignEffect) / delta ** 2;
  const nInt = Math.max(2, Math.ceil(n));
  return {
    nQuestions: nInt,
    delta,
    alpha,
    power,
    rho,
    samplesPerQuestion,
    clusterDesignEffect,
    perQuestionVariance: v,
  };
}

/** Smallest paired difference detectable with a given n, alpha, power. */
export function minimumDetectableEffect(nQuestions: number, inputs: PowerInputs): number {
  const {
    alpha = 0.05,
    power = 0.8,
    rho = 0,
    samplesPerQuestion = 1,
    clusterDesignEffect = 1,
  } = inputs;
  if (nQuestions < 2) throw new Error("nQuestions must be >= 2");
  const v = perQuestionVariance({ ...inputs, samplesPerQuestion });
  const zA = zForConfidence(1 - alpha);
  const zB = zBeta(power);
  return (zA + zB) * Math.sqrt((2 * v * (1 - rho) * clusterDesignEffect) / nQuestions);
}

/** Kish's design effect: 1 + (avgClusterSize - 1) * icc. */
export function designEffect(icc: number, avgClusterSize: number): number {
  return 1 + (avgClusterSize - 1) * icc;
}
