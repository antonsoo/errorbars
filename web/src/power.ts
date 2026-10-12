/**
 * Statistical power formulas for paired LLM eval comparisons.
 *
 * This is a formula port of `src/errorbars/power.py` in the Python
 * package — same variable names, same derivation, same defaults — kept in
 * sync by comparing against Python-generated vectors in
 * `src/power.test.ts`. See `docs/formulas.md` §11 in the main repo for the
 * derivation and the modeling caveats.
 */

import { invNormalCdf } from "./normal.ts";

export class BinaryFeasibilityError extends Error {}

export interface BinaryEffectRange {
  model: "single-answer-bernoulli";
  minimumDelta: number;
  maximumDelta: number;
  minimumInclusive: boolean;
  maximumInclusive: boolean;
}

/** Positive improvements whose joint 2x2 Bernoulli table has no negative cell.
 * Does not apply to continuous scores or averages of repeated answers.
 */
export function binaryEffectRange(baselineAccuracy: number, rho: number): BinaryEffectRange {
  if (!(baselineAccuracy > 0 && baselineAccuracy < 1)) {
    throw new Error("baselineAccuracy must be strictly between 0 and 1");
  }
  if (!(rho >= -1 && rho <= 1)) throw new Error("rho must be in [-1, 1]");
  const p = baselineAccuracy, complement = 1 - p, r = Math.abs(rho);
  let low: number, high: number;
  if (rho >= 0) {
    low = 0;
    high = rho === 0 ? complement : p * complement * (1 - r) * (1 + r) / (p + r * r * complement);
  } else {
    low = Math.max(0, (r * complement - p) * (r * complement + p) / (p + r * r * complement));
    high = (complement - r * p) * (complement + r * p) / (complement + r * r * p);
  }
  if (high <= 0 || low > high) {
    throw new BinaryFeasibilityError("This baseline and correlation permit no positive improvement for single-answer binary scores. Change the assumed correlation or baseline.");
  }
  return { model: "single-answer-bernoulli", minimumDelta: low, maximumDelta: high,
    minimumInclusive: low > 0, maximumInclusive: rho !== 0 && p + high < 1 };
}

function containsEffect(bounds: BinaryEffectRange, delta: number): boolean {
  // Relative rounding tolerance must not become a material allowance for gaps
  // near perfect pairing. In particular rho=1 never has a positive interval.
  const lowerTolerance = 16 * Number.EPSILON * Math.max(Math.abs(delta), Math.abs(bounds.minimumDelta));
  const upperTolerance = 16 * Number.EPSILON * Math.max(Math.abs(delta), Math.abs(bounds.maximumDelta));
  return Number.isFinite(delta) && delta > 0 && delta >= bounds.minimumDelta - lowerTolerance &&
    (bounds.maximumInclusive ? delta <= bounds.maximumDelta + upperTolerance : delta < bounds.maximumDelta);
}

function describeRange(bounds: BinaryEffectRange): string {
  const low = bounds.minimumDelta === 0 ? "greater than 0" : `at least ${Number((100 * bounds.minimumDelta).toPrecision(8))}`;
  const upper = bounds.maximumInclusive ? "at most" : "less than";
  return `${low} and ${upper} ${Number((100 * bounds.maximumDelta).toPrecision(8))} percentage points`;
}

function checkCount(value: number, name: string, minimum: number): void {
  if (!Number.isSafeInteger(value) || value < minimum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${Number.MAX_SAFE_INTEGER}`);
  }
}

export interface VarianceInputs {
  /** Binary metric: baseline accuracy p, giving per-sample variance p(1-p). */
  baselineAccuracy?: number;
  /** Continuous metric: raw per-sample variance. */
  variance?: number;
  samplesPerQuestion?: number;
  /** Correlation between draws from one model on the same question; required for repeats. */
  repeatCorrelation?: number;
}

export function perQuestionVariance({
  baselineAccuracy,
  variance,
  samplesPerQuestion = 1,
  repeatCorrelation,
}: VarianceInputs): number {
  if ((baselineAccuracy !== undefined) === (variance !== undefined)) {
    throw new Error("pass exactly one of baselineAccuracy or variance");
  }
  checkCount(samplesPerQuestion, "samplesPerQuestion", 1);
  if (baselineAccuracy !== undefined && !(baselineAccuracy > 0 && baselineAccuracy < 1)) {
    throw new Error(`baselineAccuracy must be strictly between 0 and 1, got ${baselineAccuracy}`);
  }
  if (variance !== undefined && !(variance > 0 && Number.isFinite(variance))) {
    throw new Error(`variance must be positive and finite, got ${variance}`);
  }
  if (repeatCorrelation !== undefined &&
      !(typeof repeatCorrelation === "number" && repeatCorrelation >= 0 && repeatCorrelation <= 1)) {
    throw new Error("repeatCorrelation must be a finite number in [0, 1]");
  }
  if (samplesPerQuestion > 1 && repeatCorrelation === undefined) {
    throw new Error("repeatCorrelation is required for samplesPerQuestion > 1; 0 assumes independent repeats, 1 assumes no variance reduction");
  }
  const v =
    baselineAccuracy !== undefined ? baselineAccuracy * (1 - baselineAccuracy) : (variance as number);
  const r = repeatCorrelation ?? 0;
  const result = samplesPerQuestion === 1 ? v : v * (r + (1 - r) / samplesPerQuestion);
  if (result <= 0) throw new Error("per-question variance is too small to represent");
  return result;
}

function zSum(alpha: number, power: number): number {
  if (!(alpha > 0 && alpha < 1)) throw new Error(`alpha must be in (0, 1), got ${alpha}`);
  if (alpha / 2 === 0) throw new Error("alpha is too small to represent its two-sided tail");
  if (!(power > 0 && power < 1)) {
    throw new Error(`power must be in (0, 1), got ${power}`);
  }
  const result = -invNormalCdf(alpha / 2) + invNormalCdf(power);
  if (result <= 0) {
    throw new Error("power is too low for this positive-effect approximation at the given alpha");
  }
  return result;
}

function checkDesign(rho: number, deff: number): void {
  if (!(rho >= -1 && rho <= 1)) throw new Error("rho must be in [-1, 1]");
  if (!(deff >= 1 && Number.isFinite(deff))) {
    throw new Error("clusterDesignEffect must be a finite number >= 1");
  }
}

function differenceSd(v: number, rho: number, deff: number): number {
  return Math.sqrt(v) * Math.sqrt(2 * (1 - rho)) * Math.sqrt(deff);
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
  repeatCorrelation: number | null;
  binaryFeasibility: BinaryEffectRange | null;
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
  if (!(delta > 0 && Number.isFinite(delta))) throw new Error("delta must be positive and finite");
  checkDesign(rho, clusterDesignEffect);

  const v = perQuestionVariance({ ...inputs, samplesPerQuestion });
  if (inputs.baselineAccuracy !== undefined && inputs.baselineAccuracy + delta > 1) {
    throw new Error(`baselineAccuracy + delta = ${(inputs.baselineAccuracy + delta).toPrecision(3)}: an accuracy can't exceed 1`);
  }
  const z = zSum(alpha, power);
  const bounds = inputs.baselineAccuracy !== undefined && samplesPerQuestion === 1
    ? binaryEffectRange(inputs.baselineAccuracy, rho) : null;
  if (bounds && (inputs.baselineAccuracy! + delta >= 1 || !containsEffect(bounds, delta))) {
    throw new BinaryFeasibilityError(`The assumed correlation permits binary improvements ${describeRange(bounds)}; the requested gap is ${Number((100 * delta).toPrecision(8))} points. Change the correlation or gap.`);
  }
  const rootN = differenceSd(v, rho, clusterDesignEffect) / delta * z;
  const nInt = Math.max(2, Math.ceil(rootN * rootN));
  if (!Number.isSafeInteger(nInt)) {
    throw new Error("required question count exceeds the exactly representable planning range");
  }
  return {
    nQuestions: nInt,
    delta,
    alpha,
    power,
    rho,
    samplesPerQuestion,
    clusterDesignEffect,
    perQuestionVariance: v,
    repeatCorrelation: inputs.repeatCorrelation ?? null,
    binaryFeasibility: bounds,
  };
}

/** Smallest feasible difference under the normal approximation. Single-answer
 * binary plans may be limited by the correlation's minimum possible gap, and
 * may have no detectable feasible gap. Other variance models are unchanged.
 */
export function minimumDetectableEffect(nQuestions: number, inputs: PowerInputs): number {
  const {
    alpha = 0.05,
    power = 0.8,
    rho = 0,
    samplesPerQuestion = 1,
    clusterDesignEffect = 1,
  } = inputs;
  checkCount(nQuestions, "nQuestions", 2);
  checkDesign(rho, clusterDesignEffect);
  const v = perQuestionVariance({ ...inputs, samplesPerQuestion });
  const z = zSum(alpha, power);
  let result = differenceSd(v, rho, clusterDesignEffect) / Math.sqrt(nQuestions) * z;
  if (!Number.isFinite(result) || (result === 0 && rho !== 1)) {
    throw new Error("minimum detectable effect is outside the representable planning range");
  }
  if (inputs.baselineAccuracy !== undefined && samplesPerQuestion === 1) {
    const bounds = binaryEffectRange(inputs.baselineAccuracy, rho);
    result = Math.max(result, bounds.minimumDelta);
    if (inputs.baselineAccuracy + result >= 1 || !containsEffect(bounds, result)) {
      throw new BinaryFeasibilityError(`This budget cannot detect a feasible binary improvement at the requested power. The assumed correlation permits gaps ${describeRange(bounds)}. Increase the budget or change the planning assumptions.`);
    }
    result = Math.min(result, bounds.maximumDelta);
  }
  return result;
}

/** Kish's design effect: 1 + (avgClusterSize - 1) * icc. */
export function designEffect(icc: number, avgClusterSize: number): number {
  if (!(icc >= 0 && icc <= 1)) throw new Error("icc must be in [0, 1]");
  if (!(Number.isFinite(avgClusterSize) && avgClusterSize >= 1)) {
    throw new Error("avgClusterSize must be finite and >= 1");
  }
  const result = 1 + (avgClusterSize - 1) * icc;
  checkDesign(0, result);
  return result;
}
