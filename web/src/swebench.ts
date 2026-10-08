import "./fonts/fonts.css";
import "./style.css";
import gapsDark from "../../studies/swe-bench-verified/figures/gaps-dark.svg";
import gapsLight from "../../studies/swe-bench-verified/figures/gaps-light.svg";
import leaderDark from "../../studies/swe-bench-verified/figures/leader-dark.svg";
import leaderLight from "../../studies/swe-bench-verified/figures/leader-light.svg";
import recordsDark from "../../studies/swe-bench-verified/figures/records-dark.svg";
import recordsLight from "../../studies/swe-bench-verified/figures/records-light.svg";
import { commit, instances, repositories, repositoryIndex, submissions, type Submission } from "./outcomes.ts";
import { pairedCompare, type PairedResult } from "./paired.ts";
import { initTheme } from "./theme.ts";

const SVG = "http://www.w3.org/2000/svg";
const OWN_ID = "own-run";
const DEFAULT_A = "20260217_mini-v2.0.0_claude-4-5-opus-high";
const DEFAULT_B = "20260217_mini-v2.0.0_gpt-5-2-high";
const ALPHA = 0.05;

function byId<T extends HTMLElement>(id: string): T {
  const element = document.getElementById(id);
  if (!element) throw new Error(`missing #${id}`);
  return element as T;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function svg(tag: string, attributes: Record<string, string | number>, text = ""): SVGElement {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  if (text) node.textContent = text;
  return node;
}

/** One format everywhere, whatever the visitor's locale. */
const percent = (share: number): string => `${(100 * share).toFixed(1)}%`;
const points = (share: number): string => (100 * share).toFixed(1);
const signed = (share: number): string => `${share < 0 ? "−" : "+"}${Math.abs(100 * share).toFixed(1)}`;
function pValue(p: number): string {
  // No-break spaces: a p-value split over two lines reads as two numbers.
  if (p < 0.0001) return "p\u00a0<\u00a00.0001";
  return `p\u00a0=\u00a0${p < 0.001 ? p.toFixed(4) : p < 0.1 ? p.toFixed(3) : p.toFixed(2)}`;
}

let ownRun: Submission | null = null;
const pickA = byId<HTMLSelectElement>("pick-a");
const pickB = byId<HTMLSelectElement>("pick-b");

function find(id: string): Submission | undefined {
  return id === OWN_ID ? (ownRun ?? undefined) : submissions.find((s) => s.id === id);
}

function fillPickers(a: string, b: string): void {
  for (const [select, chosen] of [[pickA, a], [pickB, b]] as const) {
    select.replaceChildren();
    if (ownRun && select === pickA) {
      select.append(new Option(`${percent(ownRun.score)}  ${ownRun.name} (your run)`, OWN_ID));
    }
    for (const s of submissions) {
      select.append(new Option(`${percent(s.score)}  ${s.name} · ${s.date}`, s.id));
    }
    select.value = chosen;
    if (select.selectedIndex < 0) select.selectedIndex = 0;
  }
}

/** The headline: one plain sentence, then the numbers behind it. */
function verdict(a: Submission, b: Submission, r: PairedResult): [string, string] {
  if (a === b) return ["Pick two different submissions.", "A and B are the same run, so there is nothing to compare."];
  const [ahead, behind] = r.diff >= 0 ? [a, b] : [b, a];
  const gap = points(Math.abs(r.diff));
  const scores = `${percent(ahead.score)} against ${percent(behind.score)}`;
  const differ = r.onlyA + r.onlyB;
  if (r.diff === 0) {
    return [
      "Level.",
      `Both resolve ${percent(a.score)} of the tasks. They disagree on ${differ} of them, split evenly.`,
    ];
  }
  if (r.p >= ALPHA) {
    return [
      "Not distinguishable.",
      `${ahead.name} is ${gap} points ahead of ${behind.name} (${scores}). A gap this size is within the noise of 500 tasks: ${pValue(r.p)}.`,
    ];
  }
  if (r.pClustered >= ALPHA) {
    return [
      "Different on tasks like these.",
      `${ahead.name} is ${gap} points ahead of ${behind.name} (${scores}; ${pValue(r.p)}). Whether that holds on other codebases, 12 repositories cannot say: ${pValue(r.pClustered)} with repositories as the sample.`,
    ];
  }
  return [
    "Different, on these tasks and across repositories.",
    `${ahead.name} is ${gap} points ahead of ${behind.name} (${scores}; ${pValue(r.p)}). It holds with repositories as the sample too: ${pValue(r.pClustered)}.`,
  ];
}

/** Drawn at the figure's real width, so its lettering is the same size on a phone as on a desk. */
function drawIntervals(r: PairedResult): void {
  const chart = byId("interval-chart") as unknown as SVGSVGElement;
  const width = Math.max(280, Math.round(chart.getBoundingClientRect().width) || 720);
  // Wide: labels sit in a column left of the plot. Narrow: each label sits above its interval.
  const wide = width >= 560;
  const left = wide ? 210 : 10;
  const right = width - (wide ? 24 : 10);
  const rowY = wide ? [52, 96] : [56, 116];
  const plotBottom = wide ? 118 : 138;
  const height = plotBottom + 50;
  const reach = Math.max(6, Math.ceil(Math.max(Math.abs(r.ciLowClustered), Math.abs(r.ciHighClustered), Math.abs(r.ciLow), Math.abs(r.ciHigh)) * 100 * 1.08));
  const step = reach <= 8 ? 2 : reach <= 20 ? 5 : reach <= 50 ? 10 : 25;
  const x = (share: number): number => left + ((share * 100 + reach) / (2 * reach)) * (right - left);
  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.setAttribute("height", String(height));
  chart.replaceChildren(
    svg("title", { id: "interval-title" },
      `A minus B: ${signed(r.diff)} points. Tasks as the sample: ${signed(r.ciLow)} to ${signed(r.ciHigh)}. Repositories as the sample: ${signed(r.ciLowClustered)} to ${signed(r.ciHighClustered)}.`),
  );
  for (let tick = -Math.floor(reach / step) * step; tick <= reach; tick += step) {
    const tx = x(tick / 100);
    chart.append(
      svg("line", { x1: tx, y1: 26, x2: tx, y2: plotBottom, class: tick === 0 ? "zero-line" : "grid-line" }),
      svg("text", { x: tx, y: plotBottom + 18, class: "tick-label", "text-anchor": "middle" }, tick === 0 ? "0" : `${tick < 0 ? "−" : "+"}${Math.abs(tick)}`),
    );
  }
  chart.append(
    svg("text", { x: left, y: plotBottom + 40, class: "axis-end" }, "← B ahead"),
    svg("text", { x: right, y: plotBottom + 40, class: "axis-end", "text-anchor": "end" }, "A ahead, in points →"),
  );
  const rows: [string, string, number, number][] = [
    ["Tasks as the sample", `${signed(r.ciLow)} to ${signed(r.ciHigh)}`, r.ciLow, r.ciHigh],
    ["Repositories as the sample", `${signed(r.ciLowClustered)} to ${signed(r.ciHighClustered)}`, r.ciLowClustered, r.ciHighClustered],
  ];
  rows.forEach(([label, range, low, high], i) => {
    const y = rowY[i]!;
    if (wide) {
      chart.append(
        svg("text", { x: 0, y: y - 2, class: "row-label" }, label),
        svg("text", { x: 0, y: y + 15, class: "row-range" }, range),
      );
    } else {
      chart.append(
        svg("text", { x: left, y: y - 14, class: "row-label row-label-above" }, label),
        svg("text", { x: right, y: y - 14, class: "row-range row-label-above", "text-anchor": "end" }, range),
      );
    }
    chart.append(
      svg("line", { x1: x(low), y1: y, x2: x(high), y2: y, class: "interval" }),
      svg("line", { x1: x(low), y1: y - 6, x2: x(low), y2: y + 6, class: "interval" }),
      svg("line", { x1: x(high), y1: y - 6, x2: x(high), y2: y + 6, class: "interval" }),
      svg("circle", { cx: x(r.diff), cy: y, r: 5.5, class: "estimate" }),
    );
  });
}

function fillTable(a: Submission, b: Submission, r: PairedResult): void {
  const rows: [string, string][] = [
    ["Resolved", `A ${percent(r.meanA)} (${Math.round(r.meanA * r.n)} of ${r.n}) · B ${percent(r.meanB)} (${Math.round(r.meanB * r.n)})`],
    ["Gap, A minus B", `${signed(r.diff)} points`],
    ["Tasks where they differ", `${r.onlyA + r.onlyB}: only A resolved ${r.onlyA}, only B resolved ${r.onlyB} · exact McNemar ${pValue(r.mcnemarP)}`],
    ["Tasks as the sample", `standard error ${points(r.se)} · 95% interval ${signed(r.ciLow)} to ${signed(r.ciHigh)} · ${pValue(r.p)}`],
    ["Repositories as the sample", `standard error ${points(r.seClustered)} · 95% interval ${signed(r.ciLowClustered)} to ${signed(r.ciHighClustered)} · ${pValue(r.pClustered)} · ${r.dofClustered.toFixed(1)} degrees of freedom from ${r.clusters} repositories`],
    ["Agreement", r.correlation === null ? "correlation unavailable: one run resolves all tasks or none" : `correlation of outcomes ${r.correlation.toFixed(2)}`],
  ];
  const checks = [a, b].map((s) => (s.id === OWN_ID ? "your own" : s.checked === true ? "checked by SWE-bench" : "self-reported"));
  rows.push(["Source", `A ${checks[0]} · B ${checks[1]}`]);
  const body = byId<HTMLTableElement>("result-table").tBodies[0]!;
  body.replaceChildren(
    ...rows.map(([name, value]) => {
      const row = el("tr");
      const head = el("th", "", name);
      head.scope = "row";
      row.append(head, el("td", "", value));
      return row;
    }),
  );
}

function drawTasks(a: Submission, b: Submission, r: PairedResult): void {
  const blocks = repositories.map((repo) => ({ repo, cells: [] as HTMLElement[], a: 0, b: 0, onlyA: 0, onlyB: 0 }));
  const differing: string[] = [];
  instances.forEach((instance, i) => {
    const block = blocks[repositoryIndex[i]!]!;
    const x = a.resolved[i]!;
    const y = b.resolved[i]!;
    block.a += x;
    block.b += y;
    const kind = x && y ? "both" : x ? "a" : y ? "b" : "none";
    if (kind === "a") block.onlyA++;
    if (kind === "b") block.onlyB++;
    if (kind === "a" || kind === "b") differing.push(`${instance}  only ${kind.toUpperCase()}`);
    const cell = el("span", `cell cell-${kind}`);
    cell.title = `${instance}: ${kind === "both" ? "both resolved" : kind === "none" ? "neither resolved" : `only ${kind.toUpperCase()} resolved`}`;
    block.cells.push(cell);
  });
  // Differences first within a repository, so the eye finds them without hunting.
  const order = { a: 0, b: 1, both: 2, none: 3 } as const;
  const grid = byId("task-grid");
  grid.replaceChildren(
    ...blocks.map((block) => {
      const row = el("div", "repo");
      const head = el("div", "repo-head");
      head.append(el("span", "repo-name", block.repo), el("span", "repo-count", block.cells.length === 1 ? "1 task" : `${block.cells.length} tasks`));
      const net = block.onlyA - block.onlyB;
      const summary = block.onlyA + block.onlyB === 0
        ? "no task differs"
        : `only A ${block.onlyA} · only B ${block.onlyB}${net === 0 ? "" : ` · ${net > 0 ? "A" : "B"} +${Math.abs(net)}`}`;
      head.append(el("span", "repo-net", summary));
      const cells = el("div", "repo-cells");
      cells.setAttribute("role", "img");
      cells.setAttribute("aria-label", `${block.repo}: A resolved ${block.a} of ${block.cells.length}, B ${block.b}; ${summary}`);
      block.cells.sort((p, q) => order[p.className.slice(10) as keyof typeof order] - order[q.className.slice(10) as keyof typeof order]);
      cells.append(...block.cells);
      row.append(head, cells);
      return row;
    }),
  );
  byId("discordant-summary").textContent = `List the ${r.onlyA + r.onlyB} tasks where they differ`;
  byId("discordant-list").textContent = differing.join("\n");
}

let shown: PairedResult | null = null;

function update(): void {
  const a = find(pickA.value);
  const b = find(pickB.value);
  if (!a || !b) return;
  const r = pairedCompare(a.resolved, b.resolved, repositoryIndex);
  shown = r;
  const [line, detail] = verdict(a, b, r);
  byId("verdict").textContent = line;
  byId("verdict-detail").textContent = detail;
  drawIntervals(r);
  fillTable(a, b, r);
  drawTasks(a, b, r);
  // B's list has no entry for a pasted run, so there is nothing to swap it into.
  byId<HTMLButtonElement>("swap").disabled = a.id === OWN_ID;
  const query = new URLSearchParams();
  if (a.id !== OWN_ID) query.set("a", a.id);
  query.set("b", b.id);
  history.replaceState(null, "", `?${query.toString()}`);
}

/** Resolved ids from a harness report, or from plain text with one id per line. */
function parseOwnRun(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("Paste the resolved task ids first.");
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    let report: unknown;
    try {
      report = JSON.parse(trimmed);
    } catch {
      throw new Error("That looks like JSON but does not parse. Paste the whole report, or one task id per line.");
    }
    const list = Array.isArray(report)
      ? report
      : ((report as Record<string, unknown>).resolved_ids ?? (report as Record<string, unknown>).resolved);
    if (!Array.isArray(list) || list.some((id) => typeof id !== "string")) {
      throw new Error('The report has no "resolved_ids" or "resolved" list of task ids.');
    }
    return list as string[];
  }
  return trimmed.split(/[\s,;]+/).filter(Boolean);
}

function applyOwnRun(): void {
  const status = byId("own-status");
  try {
    const ids = new Set(parseOwnRun(byId<HTMLTextAreaElement>("own-ids").value));
    const known = new Set(instances);
    const unknown = [...ids].filter((id) => !known.has(id));
    if (unknown.length) {
      throw new Error(`${unknown.length} of these are not SWE-bench Verified task ids (first: ${unknown[0]!.slice(0, 60)}). Nothing was compared.`);
    }
    const resolved = Uint8Array.from(instances, (id) => (ids.has(id) ? 1 : 0));
    ownRun = {
      id: OWN_ID,
      name: byId<HTMLInputElement>("own-name").value.trim() || "My run",
      date: "",
      resolved,
      score: ids.size / instances.length,
      checked: null,
    };
    status.className = "own-status";
    status.textContent = `Comparing your run as A: ${ids.size} of ${instances.length} tasks resolved (${percent(ownRun.score)}). Tasks you did not list count as unresolved.`;
    byId("own-clear").hidden = false;
    fillPickers(OWN_ID, pickB.value);
    update();
  } catch (error) {
    status.className = "own-status own-status-error";
    status.textContent = error instanceof Error ? error.message : "That could not be read.";
  }
}

function boardFigures(): void {
  const figures: [string, string, string, string][] = [
    [leaderLight, leaderDark, "The leader's paired advantage over each of ranks 2 to 25, with 95% intervals. The intervals for ranks 2 to 9 include zero.",
      "The leader is not distinguishable from ranks 2 to 9. None of the 49 adjacent pairs in the top 50 differ."],
    [gapsLight, gapsDark, "Share of pairs of submissions that differ significantly, by the gap between them, for tasks and for repositories as the sample.",
      "Among 3,003 pairs of strong submissions, a gap under 3 points is significant once in 874; above 4.2 points, always."],
    [recordsLight, recordsDark, "The top SWE-bench Verified score over time, with a dot for each of the 31 submissions that held it; six are marked as significantly above the one they replaced.",
      "The top score went up 30 times. Six of those new records were significantly above the record they replaced."],
  ];
  byId("board-figures").replaceChildren(
    ...figures.map(([light, dark, alt, caption]) => {
      const figure = el("figure", "board-figure");
      for (const [src, theme] of [[light, "light"], [dark, "dark"]] as const) {
        const image = el("img", `figure-${theme}`);
        image.src = src;
        image.alt = alt;
        image.loading = "lazy";
        image.width = 880;
        figure.append(image);
      }
      figure.append(el("figcaption", "", caption));
      return figure;
    }),
  );
}

initTheme(byId<HTMLButtonElement>("theme-toggle"));
byId("submission-count").textContent = String(submissions.length);
byId("commit").textContent = commit.slice(0, 7);
const query = new URLSearchParams(location.search);
fillPickers(
  find(query.get("a") ?? "")?.id ?? DEFAULT_A,
  find(query.get("b") ?? "")?.id ?? DEFAULT_B,
);
pickA.addEventListener("change", update);
pickB.addEventListener("change", update);
byId("swap").addEventListener("click", () => {
  [pickA.value, pickB.value] = [pickB.value, pickA.value];
  update();
});
byId("own-apply").addEventListener("click", applyOwnRun);
byId("own-clear").addEventListener("click", () => {
  ownRun = null;
  byId("own-clear").hidden = true;
  byId("own-status").textContent = "";
  fillPickers(DEFAULT_A, pickB.value);
  update();
});
boardFigures();
update();
new ResizeObserver(() => {
  if (shown) drawIntervals(shown);
}).observe(byId("interval-chart").parentElement!);
