import { minimumDetectableEffect, type PowerInputs } from "./power.ts";

export interface ChartPoint {
  n: number;
  mde: number;
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
  return out.filter((p, i) => i === 0 || p.n !== out[i - 1]!.n);
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
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Computed minimum detectable effect versus question count. Current plan: ${opts.current.n} questions, ${(opts.current.mde * 100).toFixed(3)} percentage points. Question count uses a logarithmic scale; exact values follow in a table.">
      ${yGridLines.join("")}
      <path class="chart-curve" d="${pathD}"/>
      <line x1="${currentX.toFixed(2)}" y1="${MARGIN.top}" x2="${currentX.toFixed(2)}" y2="${height - MARGIN.bottom}" stroke="var(--noise)" stroke-width="1" stroke-dasharray="3 3" opacity="0.6"/>
      <circle class="chart-marker" cx="${currentX.toFixed(2)}" cy="${currentY.toFixed(2)}" r="5.5"/>
      ${xLabels}
      <line x1="${MARGIN.left}" y1="${height - MARGIN.bottom}" x2="${width - MARGIN.right}" y2="${height - MARGIN.bottom}" stroke="var(--grid-strong)" stroke-width="1"/>
      <text class="chart-axis-label" x="${width / 2}" y="${height - 2}" text-anchor="middle">questions (log scale)</text>
    </svg>
  `;
}
