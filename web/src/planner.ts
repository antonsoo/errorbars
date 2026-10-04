import { designEffect, minimumDetectableEffect, perQuestionVariance, questionsNeeded } from "./power.ts";

export type PlanMode = "questions" | "budget";
export type Field = "baseline" | "delta" | "budget" | "rho" | "clusterSize" | "icc" | "alpha" | "power";
export interface FieldSpec {
  key: Field;
  label: string;
  caption: string;
  min: number;
  max: number;
  step: number;
  initial: number;
  integer?: boolean;
}

// Percentages in the editors; fractions at the formula boundary and in exported inputs.
export const FIELDS: readonly FieldSpec[] = [
  { key: "baseline", label: "Baseline accuracy (%)", caption: "Sets the planning variance p(1-p) for both models.", min: 0.1, max: 99.9, step: 0.1, initial: 50 },
  { key: "delta", label: "Gap to detect (percentage points)", caption: "An improvement of 3 points means 50% to 53% accuracy.", min: 0.01, max: 50, step: 0.01, initial: 3 },
  { key: "budget", label: "Available questions", caption: "Distinct questions answered by each of the two models.", min: 2, max: 1_000_000_000, step: 1, initial: 500, integer: true },
  { key: "rho", label: "Paired correlation", caption: "Correlation between the two models' scores on the same questions. Use 0 if unknown.", min: -0.95, max: 0.95, step: 0.01, initial: 0.3 },
  { key: "clusterSize", label: "Average cluster size", caption: "Questions per shared passage or group. Use 1 for independent questions.", min: 1, max: 1000, step: 1, initial: 1 },
  { key: "icc", label: "Intraclass correlation (ICC)", caption: "Similarity within a group. Has no effect when cluster size is 1.", min: 0, max: 1, step: 0.01, initial: 0 },
  { key: "alpha", label: "Significance level (%)", caption: "Two-sided false-positive rate for this single comparison.", min: 0.1, max: 20, step: 0.1, initial: 5 },
  { key: "power", label: "Target power (%)", caption: "Chance of detecting the gap under the planning assumptions.", min: 50, max: 99.9, step: 0.1, initial: 80 },
];

export type Values = Record<Field, number>;
export const defaults = (): Values => Object.fromEntries(FIELDS.map(f => [f.key, f.initial])) as Values;
export const isActive = (key: Field, mode: PlanMode): boolean => key !== (mode === "questions" ? "budget" : "delta");

export class PlanInputError extends Error {
  constructor(public readonly field: Field, message: string) { super(message); }
}

export const ASSUMPTIONS = [
  "Normal approximation for one two-sided paired comparison; this is a planning estimate, not a guarantee.",
  "Binary scores with the same planning variance p(1-p) for both models; one answer per model per question.",
  "Pairing correlation and within-group ICC are assumptions, not estimates from observed data.",
  "Clustering uses 1 + (average cluster size - 1) * ICC. Unequal groups and few independent groups can need a different design.",
  "The model does not enforce joint Bernoulli feasibility for the assumed correlation and changed accuracy. Validate near-boundary or large-gap plans with a pilot or simulation.",
] as const;

export function plan(mode: PlanMode, values: Values) {
  for (const f of FIELDS) {
    if (!isActive(f.key, mode)) continue;
    const value = values[f.key];
    if (!Number.isFinite(value) || value < f.min || value > f.max || (f.integer && !Number.isSafeInteger(value))) {
      throw new PlanInputError(f.key, `${f.label}: enter ${f.integer ? "a whole number" : "a number"} from ${f.min} to ${f.max}.`);
    }
  }
  const baselineAccuracy = values.baseline / 100;
  const delta = values.delta / 100;
  if (mode === "questions" && baselineAccuracy + delta > 1) {
    throw new PlanInputError("delta", `The requested improvement exceeds 100% accuracy. Reduce the gap to at most ${Number((100 - values.baseline).toFixed(10))} points, or lower the baseline.`);
  }
  const clusterDesignEffect = designEffect(values.icc, values.clusterSize);
  const inputs = {
    baselineAccuracy,
    alpha: values.alpha / 100,
    power: values.power / 100,
    rho: values.rho,
    samplesPerQuestion: 1,
    clusterDesignEffect,
  };
  const n = mode === "questions" ? questionsNeeded(delta, inputs).nQuestions : values.budget;
  const mde = minimumDetectableEffect(n, inputs);
  const maxImprovement = 1 - baselineAccuracy;
  const withoutPairing = { ...inputs, rho: 0 };
  const sensitivityN = mode === "questions" ? questionsNeeded(delta, withoutPairing).nQuestions : n;
  const warnings: string[] = [];
  if (mde > maxImprovement) warnings.push("This budget cannot detect an achievable accuracy improvement under these assumptions: the estimated gap exceeds the distance to 100%.");
  if (n < 30) warnings.push("Fewer than 30 questions: the normal approximation may be unreliable. Check the proposed design by simulation.");
  if (values.clusterSize > 1 && n / values.clusterSize < 30) warnings.push("Fewer than 30 groups at this average cluster size. The normal approximation does not account for small-group uncertainty.");
  return {
    format: "errorbars-plan" as const,
    schemaVersion: 1 as const,
    method: "paired-normal-approximation-v1" as const,
    mode,
    inputs: {
      ...inputs,
      averageClusterSize: values.clusterSize,
      intraclassCorrelation: values.icc,
      targetDifference: mode === "questions" ? delta : null,
      availableQuestions: mode === "budget" ? n : null,
    },
    result: {
      nQuestions: n,
      minimumDetectableEffect: mde,
      maximumImprovement: maxImprovement,
      achievableImprovement: mde <= maxImprovement,
      modelAnswers: n * 2,
      approximateGroups: n / values.clusterSize,
      perQuestionVariance: perQuestionVariance(inputs),
    },
    sensitivity: {
      rho: 0,
      nQuestions: sensitivityN,
      minimumDetectableEffect: minimumDetectableEffect(sensitivityN, withoutPairing),
    },
    units: { accuracy: "fraction", difference: "fraction (multiply by 100 for percentage points)", questions: "distinct questions per model", modelAnswers: "one answer per question from each of two models" },
    assumptions: ASSUMPTIONS,
    warnings,
    cliCommand: `errorbars power ${mode === "questions" ? `--delta ${delta}` : `--n ${n}`} --baseline ${baselineAccuracy} --rho ${inputs.rho} --alpha ${inputs.alpha} --power ${inputs.power} --cluster-deff ${clusterDesignEffect} --samples-per-question 1 --json`,
  };
}

export type Plan = ReturnType<typeof plan>;
