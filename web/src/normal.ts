/**
 * Inverse standard normal CDF using Wichura's AS241 rational approximation.
 * Adapted from CPython 3.12's Lib/statistics.py (_normal_dist_inv_cdf).
 * See THIRD_PARTY_NOTICES.md and LICENSES/Python-2.0.txt for provenance and license.
 * Independent SciPy quantiles and live Python vectors exercise all three regions.
 */

export function invNormalCdf(p: number): number {
  if (!(p > 0 && p < 1)) {
    throw new RangeError(`invNormalCdf: p must be in (0, 1), got ${p}`);
  }
  const q = p - 0.5;
  if (Math.abs(q) <= 0.425) {
    const r = 0.180625 - q * q;
    const num = (((((((2509.0809287301227 * r +
      33430.57558358813) * r +
      67265.7709270087) * r +
      45921.95393154987) * r +
      13731.69376550946) * r +
      1971.5909503065513) * r +
      133.14166789178438) * r +
      3.3871328727963665) * q;
    const den = ((((((5226.495278852854 * r +
      28729.085735721943) * r +
      39307.89580009271) * r +
      21213.794301586597) * r +
      5394.196021424751) * r +
      687.1870074920579) * r +
      42.31333070160091) * r +
      1.0;
    return num / den;
  }
  let r = Math.sqrt(-Math.log(q <= 0 ? p : 1 - p));
  let num: number;
  let den: number;
  if (r <= 5) {
    r -= 1.6;
    num = ((((((0.0007745450142783414 * r +
      0.022723844989269184) * r +
      0.2417807251774506) * r +
      1.2704582524523684) * r +
      3.6478483247632045) * r +
      5.769497221460691) * r +
      4.630337846156546) * r +
      1.4234371107496835;
    den = ((((((1.0507500716444169e-09 * r +
      0.0005475938084995345) * r +
      0.015198666563616457) * r +
      0.14810397642748008) * r +
      0.6897673349851) * r +
      1.6763848301838038) * r +
      2.053191626637759) * r +
      1.0;
  } else {
    r -= 5;
    num = ((((((2.0103343992922881e-07 * r +
      2.7115555687434876e-05) * r +
      0.0012426609473880784) * r +
      0.026532189526576124) * r +
      0.29656057182850487) * r +
      1.7848265399172913) * r +
      5.463784911164114) * r +
      6.657904643501103;
    den = ((((((2.0442631033899397e-15 * r +
      1.421511758316446e-07) * r +
      1.8463183175100548e-05) * r +
      0.0007868691311456133) * r +
      0.014875361290850615) * r +
      0.1369298809227358) * r +
      0.599832206555888) * r +
      1.0;
  }
  return (q < 0 ? -num : num) / den;
}

/** Two-sided normal critical value, e.g. about 1.96 at confidence 0.95. */
export function zForConfidence(confidence: number): number {
  if (!(confidence > 0 && confidence < 1)) {
    throw new RangeError(`zForConfidence: confidence must be in (0, 1), got ${confidence}`);
  }
  return -invNormalCdf((1 - confidence) / 2);
}
