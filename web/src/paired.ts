// A paired comparison of two systems scored pass/fail on the same tasks, with the tasks
// grouped into clusters. A port of errorbars.compare.paired_compare for binary scores.
import { tCritical, tTwoSidedP } from "./tdist.ts";

export interface PairedResult {
  n: number;
  meanA: number;
  meanB: number;
  /** meanA - meanB. */
  diff: number;
  /** Tasks as the sample: paired t-test on n - 1 degrees of freedom. */
  se: number;
  ciLow: number;
  ciHigh: number;
  p: number;
  /** Null when either system resolved all tasks or none. */
  correlation: number | null;
  /** Tasks only A resolved, tasks only B resolved, and the exact McNemar test on them. */
  onlyA: number;
  onlyB: number;
  mcnemarP: number;
  /** Clusters as the sample: CR2 standard error on Satterthwaite degrees of freedom. */
  clusters: number;
  dofClustered: number;
  seClustered: number;
  ciLowClustered: number;
  ciHighClustered: number;
  pClustered: number;
}

function pFor(mean: number, se: number, dof: number): number {
  if (se === 0) return mean === 0 ? 1 : 0;
  return tTwoSidedP(mean / se, dof);
}

/** Exact two-sided binomial test that the discordant pairs split evenly. */
export function mcnemarExact(onlyA: number, onlyB: number): number {
  const total = onlyA + onlyB;
  const k = Math.min(onlyA, onlyB);
  if (total === 0 || 2 * k >= total - 1) return 1;
  // C(total, i) / 2^total, built from its neighbour; 2^-total is representable to total = 1074.
  let term = 0.5 ** total;
  let tail = term;
  for (let i = 1; i <= k; i++) {
    term *= (total - i + 1) / i;
    tail += term;
  }
  return Math.min(1, 2 * tail);
}

/** Satterthwaite degrees of freedom of a CR2 clustered mean; depends on cluster sizes only. */
export function clusterDegreesOfFreedom(sizes: readonly number[]): number {
  const n = sizes.reduce((sum, size) => sum + size, 0);
  let squares = 0;
  let weighted = 0;
  let weightedSquares = 0;
  for (const size of sizes) {
    const c = 1 / (1 - size / n);
    squares += size * size;
    weighted += c * size * size;
    weightedSquares += c * c * size ** 4;
  }
  return (n * n) / (squares + (weighted * weighted - weightedSquares) / (n * n));
}

/**
 * `a` and `b` hold 0 or 1 per task; `cluster` holds each task's cluster as an index from 0.
 */
export function pairedCompare(
  a: ArrayLike<number>,
  b: ArrayLike<number>,
  cluster: ArrayLike<number>,
  confidence = 0.95,
): PairedResult {
  const n = a.length;
  if (b.length !== n || cluster.length !== n) throw new RangeError("inputs must have the same length");
  if (n < 2) throw new RangeError("need at least 2 paired tasks");
  let sumA = 0;
  let sumB = 0;
  let both = 0;
  let onlyA = 0;
  let onlyB = 0;
  for (let i = 0; i < n; i++) {
    const x = a[i]!;
    const y = b[i]!;
    sumA += x;
    sumB += y;
    if (x && y) both++;
    else if (x) onlyA++;
    else if (y) onlyB++;
  }
  const meanA = sumA / n;
  const meanB = sumB / n;
  const diff = meanA - meanB;

  // Differences are -1, 0 or 1, so their sum of squares is the discordant count.
  const sumSquares = onlyA + onlyB - n * diff * diff;
  const se = Math.sqrt(Math.max(sumSquares, 0) / (n - 1) / n);
  const critical = tCritical(confidence, n - 1);

  const varA = meanA * (1 - meanA);
  const varB = meanB * (1 - meanB);
  const correlation = varA > 0 && varB > 0 ? (both / n - meanA * meanB) / Math.sqrt(varA * varB) : null;

  let clusterCount = 0;
  for (let i = 0; i < n; i++) clusterCount = Math.max(clusterCount, cluster[i]! + 1);
  if (clusterCount < 2) throw new RangeError("need at least 2 clusters");
  const sizes = new Array<number>(clusterCount).fill(0);
  const residualSums = new Array<number>(clusterCount).fill(0);
  for (let i = 0; i < n; i++) {
    const g = cluster[i]!;
    sizes[g] = sizes[g]! + 1;
    residualSums[g] = residualSums[g]! + (a[i]! - b[i]! - diff);
  }
  let meat = 0;
  for (let g = 0; g < clusterCount; g++) meat += residualSums[g]! ** 2 / (1 - sizes[g]! / n);
  const seClustered = Math.sqrt(meat) / n;
  const dofClustered = clusterDegreesOfFreedom(sizes);
  const criticalClustered = tCritical(confidence, dofClustered);

  return {
    n,
    meanA,
    meanB,
    diff,
    se,
    ciLow: diff - critical * se,
    ciHigh: diff + critical * se,
    p: pFor(diff, se, n - 1),
    correlation,
    onlyA,
    onlyB,
    mcnemarP: mcnemarExact(onlyA, onlyB),
    clusters: clusterCount,
    dofClustered,
    seClustered,
    ciLowClustered: diff - criticalClustered * seClustered,
    ciHighClustered: diff + criticalClustered * seClustered,
    pClustered: pFor(diff, seClustered, dofClustered),
  };
}
