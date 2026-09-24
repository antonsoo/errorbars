import "./style.css";
import { questionsNeeded, designEffect, type PowerInputs } from "./power.ts";
import { buildCurve, renderChart } from "./chart.ts";
import { invNormalCdf, zForConfidence } from "./normal.ts";

interface SliderConfig {
  id: string;
  label: string;
  caption: string;
  min: number;
  max: number;
  step: number;
  default: number;
  format: (v: number) => string;
}

const SLIDERS: SliderConfig[] = [
  {
    id: "baseline",
    label: "Baseline accuracy",
    caption: "Roughly where your models score. Sets the per-question variance.",
    min: 0.1,
    max: 0.95,
    step: 0.01,
    default: 0.5,
    format: (v) => `${Math.round(v * 100)}%`,
  },
  {
    id: "delta",
    label: "Effect size (δ)",
    caption: "The accuracy gap you want to be able to detect.",
    min: 0.005,
    max: 0.2,
    step: 0.001,
    default: 0.03,
    format: (v) => `${(v * 100).toFixed(1)} pt`,
  },
  {
    id: "rho",
    label: "Correlation (ρ)",
    caption: "How correlated the two models' per-question scores are.",
    min: 0,
    max: 0.95,
    step: 0.01,
    default: 0.3,
    format: (v) => v.toFixed(2),
  },
  {
    id: "clusterSize",
    label: "Cluster size",
    caption: "Questions per group (e.g. per reading passage). 1 = no clustering.",
    min: 1,
    max: 20,
    step: 1,
    default: 1,
    format: (v) => `${v} q/cluster`,
  },
  {
    id: "icc",
    label: "Intraclass correlation (ICC)",
    caption: "How much questions in the same cluster resemble each other.",
    min: 0,
    max: 0.9,
    step: 0.01,
    default: 0,
    format: (v) => v.toFixed(2),
  },
  {
    id: "alpha",
    label: "Significance level (α)",
    caption: "False-positive rate you're willing to accept.",
    min: 0.01,
    max: 0.2,
    step: 0.01,
    default: 0.05,
    format: (v) => v.toFixed(2),
  },
  {
    id: "power",
    label: "Power (1 − β)",
    caption: "Chance of detecting the effect, if it's real.",
    min: 0.5,
    max: 0.99,
    step: 0.01,
    default: 0.8,
    format: (v) => `${Math.round(v * 100)}%`,
  },
];

const state: Record<string, number> = Object.fromEntries(SLIDERS.map((s) => [s.id, s.default]));

function buildControls(container: HTMLElement): void {
  for (const cfg of SLIDERS) {
    const wrap = document.createElement("div");
    wrap.className = "control";

    const head = document.createElement("div");
    head.className = "control-head";

    const label = document.createElement("label");
    label.className = "control-label";
    label.htmlFor = cfg.id;
    label.textContent = cfg.label;

    const value = document.createElement("span");
    value.className = "control-value";
    value.id = `${cfg.id}-value`;
    value.textContent = cfg.format(cfg.default);

    head.append(label, value);

    const input = document.createElement("input");
    input.type = "range";
    input.id = cfg.id;
    input.min = String(cfg.min);
    input.max = String(cfg.max);
    input.step = String(cfg.step);
    input.value = String(cfg.default);
    input.setAttribute("aria-describedby", `${cfg.id}-caption`);
    input.addEventListener("input", () => {
      state[cfg.id] = Number(input.value);
      value.textContent = cfg.format(state[cfg.id]!);
      update();
    });

    const caption = document.createElement("p");
    caption.className = "control-caption";
    caption.id = `${cfg.id}-caption`;
    caption.textContent = cfg.caption;

    wrap.append(head, input, caption);
    container.appendChild(wrap);
  }
}

function currentInputs(): PowerInputs {
  const deff = designEffect(state.icc!, state.clusterSize!);
  return {
    baselineAccuracy: state.baseline!,
    alpha: state.alpha!,
    power: state.power!,
    rho: state.rho!,
    clusterDesignEffect: deff,
  };
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function formatN(n: number): string {
  return n.toLocaleString("en-US");
}

function update(): void {
  const inputs = currentInputs();
  const result = questionsNeeded(state.delta!, inputs);
  const deff = inputs.clusterDesignEffect ?? 1;

  const nEl = document.getElementById("result-n")!;
  nEl.textContent = formatN(result.nQuestions);

  const sentenceEl = document.getElementById("result-sentence")!;
  const clusterClause =
    state.clusterSize! > 1 && state.icc! > 0
      ? ` Clustering (${state.clusterSize} questions/group, ICC=${state.icc!.toFixed(2)}) inflates that by ${deff.toFixed(2)}×.`
      : "";
  sentenceEl.innerHTML =
    `With a baseline accuracy of ${pct(state.baseline!)} and a paired correlation of ${state.rho!.toFixed(2)}, ` +
    `you need <strong>${formatN(result.nQuestions)} questions</strong> to detect a ${(state.delta! * 100).toFixed(1)}-point ` +
    `gap with ${pct(state.power!)} power at α=${state.alpha!.toFixed(2)}.` +
    clusterClause;

  const chartContainer = document.getElementById("chart")!;
  const nMin = 8;
  const nMax = Math.max(200, result.nQuestions * 4);
  const curve = buildCurve(inputs, nMin, nMax);
  renderChart(chartContainer, curve, { current: { n: result.nQuestions, mde: state.delta! } });

  const zAlpha = zForConfidence(1 - inputs.alpha!);
  const zBeta = invNormalCdf(inputs.power!);
  const detailStrip = document.getElementById("detail-strip")!;
  const details: [string, string][] = [
    ["z(α/2)", zAlpha.toFixed(3)],
    ["z(β)", zBeta.toFixed(3)],
    ["per-question variance", result.perQuestionVariance.toFixed(4)],
    ["design effect", deff.toFixed(3)],
  ];
  detailStrip.innerHTML = details
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
    .join("");
}

const controlsEl = document.getElementById("controls");
if (controlsEl) {
  buildControls(controlsEl);
  update();
}
