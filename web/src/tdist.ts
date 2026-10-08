// Student-t tails without a dependency: a port of errorbars.stats (Python), which the
// test suite checks it against. Derivations are in docs/formulas.md.

/** ln Γ(x) for x > 0 (Lanczos, g = 7, nine terms; about 15 significant digits). */
function logGamma(x: number): number {
  const coefficients = [
    0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6,
    1.5056327351493116e-7,
  ];
  if (x < 0.5) {
    // Reflection keeps the series in its accurate range.
    return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
  }
  const shifted = x - 1;
  let sum = coefficients[0]!;
  for (let i = 1; i < coefficients.length; i++) sum += coefficients[i]! / (shifted + i);
  const t = shifted + 7.5;
  return 0.5 * Math.log(2 * Math.PI) + (shifted + 0.5) * Math.log(t) - t + Math.log(sum);
}

/** Continued fraction for the incomplete beta function (modified Lentz method). */
function betaContinuedFraction(a: number, b: number, x: number): number {
  const tiny = 1e-300;
  const qab = a + b;
  const qap = a + 1;
  const qam = a - 1;
  let c = 1;
  let d = 1 - (qab * x) / qap;
  d = 1 / (Math.abs(d) > tiny ? d : tiny);
  let h = d;
  for (let m = 1; m < 1000; m++) {
    const m2 = 2 * m;
    const even = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    const odd = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    for (const term of [even, odd]) {
      d = 1 + term * d;
      d = 1 / (Math.abs(d) > tiny ? d : tiny);
      c = 1 + term / c;
      c = Math.abs(c) > tiny ? c : tiny;
      h *= d * c;
    }
    if (Math.abs(d * c - 1) < 1e-15) break;
  }
  return h;
}

/** I_x(a, b), the regularized incomplete beta function, for a, b > 0. */
export function regularizedIncompleteBeta(a: number, b: number, x: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const front = Math.exp(
    logGamma(a + b) - logGamma(a) - logGamma(b) + a * Math.log(x) + b * Math.log1p(-x),
  );
  // The fraction converges fast below (a + 1) / (a + b + 2); use symmetry above it.
  if (x < (a + 1) / (a + b + 2)) return (front * betaContinuedFraction(a, b, x)) / a;
  return 1 - (front * betaContinuedFraction(b, a, 1 - x)) / b;
}

/** Two-sided p-value of a Student-t statistic: P(|T| >= |t|). */
export function tTwoSidedP(t: number, dof: number): number {
  if (!(dof > 0)) throw new RangeError("degrees of freedom must be positive");
  if (!Number.isFinite(t)) return 0;
  return regularizedIncompleteBeta(dof / 2, 0.5, dof / (dof + t * t));
}

/** Two-sided Student-t critical value, by bisection on `tTwoSidedP`. */
export function tCritical(confidence: number, dof: number): number {
  if (!(confidence > 0 && confidence < 1)) throw new RangeError("confidence must be in (0, 1)");
  const alpha = 1 - confidence;
  let low = 0;
  let high = 10;
  while (tTwoSidedP(high, dof) > alpha) high *= 2;
  for (let i = 0; i < 200 && high - low > 1e-12; i++) {
    const mid = (low + high) / 2;
    if (tTwoSidedP(mid, dof) > alpha) low = mid;
    else high = mid;
  }
  return (low + high) / 2;
}
