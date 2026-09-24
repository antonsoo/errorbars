import { minimumDetectableEffect, type PowerInputs } from "./power.ts";

export interface ChartPoint {
  n: number;
  mde: number;
}

/** Mulberry32: tiny deterministic PRNG so the "noise" scatter is stable
 * across re-renders of the same inputs (no jitter on every slider tick). */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function buildCurve(inputs: PowerInputs, nMin: number, nMax: number, points = 60): ChartPoint[] {
  const logMin = Math.log10(nMin);
  const logMax = Math.log10(nMax);
  const out: ChartPoint[] = [];
  for (let i = 0; i < points; i++) {
    const logN = logMin + ((logMax - logMin) * i) / (points - 1);
    const n = Math.round(10 ** logN);
    out.push({ n, mde: minimumDetectableEffect(Math.max(2, n), inputs) });
  }
  return out;
}

interface RenderOptions {
  width?: number;
  height?: number;
  current: ChartPoint;
}

const MARGIN = { top: 14, right: 18, bottom: 30, left: 46 };

export function renderChart(container: HTMLElement, curve: ChartPoint[], opts: RenderOptions): void {
  const width = opts.width ?? 560;
  const height = opts.height ?? 280;
  const plotW = width - MARGIN.left - MARGIN.right;
  const plotH = height - MARGIN.top - MARGIN.bottom;

  const nMin = curve[0]!.n;
  const nMax = curve[curve.length - 1]!.n;
  const mdeMax = Math.max(...curve.map((p) => p.mde), opts.current.mde) * 1.08;

  const xScale = (n: number) => {
    const t = (Math.log10(n) - Math.log10(nMin)) / (Math.log10(nMax) - Math.log10(nMin));
    return MARGIN.left + t * plotW;
  };
  const yScale = (mde: number) => MARGIN.top + (1 - mde / mdeMax) * plotH;

  const pathD = curve
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xScale(p.n).toFixed(2)} ${yScale(p.mde).toFixed(2)}`)
    .join(" ");

  // Decorative "noise resolving into signal" scatter: points near the curve,
  // jittered more at small n (high variance) and less at large n — the
  // page's own thesis, drawn.
  const rand = mulberry32(Math.round(nMin * 7 + nMax * 13 + curve[0]!.mde * 100000));
  const noisePoints: string[] = [];
  for (let i = 0; i < 90; i++) {
    const t = rand();
    const idx = Math.min(curve.length - 1, Math.floor(t * curve.length));
    const { n, mde: baseMde } = curve[idx]!;
    const jitterScale = (1 - t) * 0.55 + 0.03; // more jitter at small n
    const jitter = (rand() - 0.5) * 2 * baseMde * jitterScale;
    const mdeJittered = Math.max(0.0005, baseMde + jitter);
    if (mdeJittered > mdeMax) continue;
    noisePoints.push(
      `<circle class="chart-noise-point" cx="${xScale(n).toFixed(2)}" cy="${yScale(mdeJittered).toFixed(2)}" r="1.6"/>`,
    );
  }

  // gridlines + y-axis ticks (MDE, as accuracy points)
  const yTicks = 4;
  const yGridLines: string[] = [];
  for (let i = 0; i <= yTicks; i++) {
    const mde = (mdeMax * i) / yTicks;
    const y = yScale(mde);
    yGridLines.push(
      `<line class="chart-grid-line" x1="${MARGIN.left}" y1="${y.toFixed(2)}" x2="${width - MARGIN.right}" y2="${y.toFixed(2)}"/>`,
      `<text class="chart-axis-label" x="${MARGIN.left - 8}" y="${(y + 3).toFixed(2)}" text-anchor="end">${(mde * 100).toFixed(1)}pt</text>`,
    );
  }

  // x-axis ticks at nice powers of ten within range
  const xTicks: number[] = [];
  for (let p = Math.ceil(Math.log10(nMin)); p <= Math.floor(Math.log10(nMax)); p++) {
    xTicks.push(10 ** p);
  }
  if (xTicks.length < 2) xTicks.push(nMin, nMax);
  const xLabels = xTicks
    .map(
      (n) =>
        `<text class="chart-axis-label" x="${xScale(n).toFixed(2)}" y="${height - MARGIN.bottom + 16}" text-anchor="middle">${n >= 1000 ? `${n / 1000}k` : n}</text>`,
    )
    .join("");

  const currentX = xScale(opts.current.n);
  const currentY = yScale(opts.current.mde);

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Minimum detectable effect versus number of questions, on a log scale x-axis">
      ${yGridLines.join("")}
      ${noisePoints.join("")}
      <path class="chart-curve" d="${pathD}"/>
      <line x1="${currentX.toFixed(2)}" y1="${MARGIN.top}" x2="${currentX.toFixed(2)}" y2="${height - MARGIN.bottom}" stroke="var(--noise)" stroke-width="1" stroke-dasharray="3 3" opacity="0.6"/>
      <circle class="chart-marker" cx="${currentX.toFixed(2)}" cy="${currentY.toFixed(2)}" r="5.5"/>
      ${xLabels}
      <line x1="${MARGIN.left}" y1="${height - MARGIN.bottom}" x2="${width - MARGIN.right}" y2="${height - MARGIN.bottom}" stroke="var(--grid-strong)" stroke-width="1"/>
      <text class="chart-axis-label" x="${width / 2}" y="${height - 2}" text-anchor="middle">questions (log scale)</text>
    </svg>
  `;
}
