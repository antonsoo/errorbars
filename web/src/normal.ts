/**
 * Inverse standard normal CDF (probit function), Peter Acklam's rational
 * approximation. Relative error < 1.15e-9 everywhere, which is what lets
 * the TypeScript power formulas agree with Python's
 * `statistics.NormalDist.inv_cdf` (also its own independent implementation,
 * not a scipy/statsmodels call) to the precision this calculator needs.
 *
 * Reference: https://web.archive.org/web/20151030215612/http://home.online.no/~pjacklam/notes/invnorm/
 */

const A = [
  -3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2, 1.38357751867269e2,
  -3.066479806614716e1, 2.506628277459239,
];
const B = [
  -5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2, 6.680131188771972e1,
  -1.328068155288572e1,
];
const C = [
  -7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838, -2.549732539343734,
  4.374664141464968, 2.938163982698783,
];
const D = [
  7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996, 3.754408661907416,
];

const P_LOW = 0.02425;
const P_HIGH = 1 - P_LOW;

/** Inverse standard normal CDF: returns z such that Phi(z) = p, for p in (0, 1). */
export function invNormalCdf(p: number): number {
  if (p <= 0 || p >= 1) {
    throw new RangeError(`invNormalCdf: p must be in (0, 1), got ${p}`);
  }
  let q: number, r: number;
  if (p < P_LOW) {
    q = Math.sqrt(-2 * Math.log(p));
    return (
      (((((C[0]! * q + C[1]!) * q + C[2]!) * q + C[3]!) * q + C[4]!) * q + C[5]!) /
      ((((D[0]! * q + D[1]!) * q + D[2]!) * q + D[3]!) * q + 1)
    );
  } else if (p <= P_HIGH) {
    q = p - 0.5;
    r = q * q;
    return (
      ((((( A[0]! * r + A[1]!) * r + A[2]!) * r + A[3]!) * r + A[4]!) * r + A[5]!) *
      q /
      (((((B[0]! * r + B[1]!) * r + B[2]!) * r + B[3]!) * r + B[4]!) * r + 1)
    );
  } else {
    q = Math.sqrt(-2 * Math.log(1 - p));
    return (
      -(((((C[0]! * q + C[1]!) * q + C[2]!) * q + C[3]!) * q + C[4]!) * q + C[5]!) /
      ((((D[0]! * q + D[1]!) * q + D[2]!) * q + D[3]!) * q + 1)
    );
  }
}

/** z_{alpha/2}: two-sided critical value, e.g. ~1.96 for confidence=0.95. */
export function zForConfidence(confidence: number): number {
  if (confidence <= 0 || confidence >= 1) {
    throw new RangeError(`zForConfidence: confidence must be in (0, 1), got ${confidence}`);
  }
  return invNormalCdf(0.5 + confidence / 2);
}
