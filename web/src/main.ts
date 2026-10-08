import "./fonts/fonts.css";
import "./style.css";
import { minimumDetectableEffect } from "./power.ts";
import { buildCurve, renderChart } from "./chart.ts";
import { initTheme } from "./theme.ts";
import { ASSUMPTIONS, defaults, FIELDS, isActive, plan, PlanInputError, type Field, type Plan, type PlanMode } from "./planner.ts";

const byId = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const number = (n: number): string => n.toLocaleString("en-US", { maximumFractionDigits: 3 });
const points = (n: number): string => `${number(n * 100)} points`;
let values = defaults();
let mode: PlanMode = "questions";
let currentPlan: Plan | null = null;
let chartWidth = 0;

function buildControls(): void {
  for (const cfg of FIELDS) {
    const wrap = document.createElement("div");
    wrap.className = "control";
    wrap.id = `${cfg.key}-control`;
    const head = document.createElement("div");
    head.className = "control-head";
    const label = document.createElement("label");
    label.className = "control-label";
    label.htmlFor = cfg.key;
    label.textContent = cfg.label;
    const input = document.createElement("input");
    input.type = "number";
    input.id = cfg.key;
    input.min = String(cfg.min);
    input.max = String(cfg.max);
    input.step = cfg.integer ? "1" : "any";
    input.value = String(cfg.initial);
    input.setAttribute("aria-describedby", `${cfg.key}-caption input-error`);
    const caption = document.createElement("p");
    caption.className = "control-caption";
    caption.id = `${cfg.key}-caption`;
    caption.textContent = cfg.caption;
    head.append(label, input);
    wrap.append(head);
    // A linear billion-question slider would be unusable; budget uses the exact editor only.
    if (cfg.key !== "budget") {
      const range = document.createElement("input");
      range.type = "range";
      range.id = `${cfg.key}-range`;
      range.min = String(cfg.min);
      range.max = String(cfg.max);
      range.step = String(cfg.step);
      range.value = input.value;
      range.setAttribute("aria-label", `Adjust ${cfg.label.toLowerCase()}`);
      range.setAttribute("aria-describedby", caption.id);
      range.setAttribute("aria-valuetext", `${input.value} ${cfg.label.includes("%") ? "percent" : cfg.key === "delta" ? "percentage points" : ""}`);
      range.addEventListener("input", () => {
        input.value = range.value;
        edit(cfg.key, input.valueAsNumber);
      });
      wrap.append(range);
    }
    input.addEventListener("input", () => edit(cfg.key, input.valueAsNumber));
    wrap.append(caption);
    byId("controls").append(wrap);
  }
}

function edit(key: Field, value: number): void {
  values[key] = value;
  const range = byId<HTMLInputElement>(`${key}-range`);
  if (range && Number.isFinite(value)) {
    range.value = String(value);
    // The number editor can be more precise than the slider's step. Announce the actual slider value.
    range.setAttribute("aria-valuetext", `${range.value} ${key === "baseline" || key === "alpha" || key === "power" ? "percent" : key === "delta" ? "percentage points" : ""}`);
  }
  update();
}

function update(): void {
  for (const cfg of FIELDS) {
    const active = isActive(cfg.key, mode);
    byId(`${cfg.key}-control`).hidden = !active;
    byId<HTMLInputElement>(cfg.key).disabled = !active;
    byId(cfg.key).removeAttribute("aria-invalid");
  }
  byId("action-status").textContent = "";
  try {
    const result = plan(mode, values);
    render(result);
    currentPlan = result;
    byId("input-error").hidden = true;
    byId("plan-output").hidden = false;
    byId<HTMLAnchorElement>("mobile-result").href = "#plan-output";
    byId("mobile-result").textContent = mode === "questions"
      ? `View plan: ${number(result.result.nQuestions)} questions per model`
      : `View plan: ${points(result.result.minimumDetectableEffect)} detectable gap`;
    byId<HTMLButtonElement>("download-plan").disabled = false;
  } catch (error) {
    currentPlan = null;
    const message = error instanceof Error ? error.message : "Unable to calculate this plan. Check the inputs.";
    byId("input-error").textContent = message;
    byId("input-error").hidden = false;
    if (error instanceof PlanInputError) byId(error.field).setAttribute("aria-invalid", "true");
    byId("plan-output").hidden = true;
    byId("result-status").textContent = "Plan unavailable. Correct the highlighted input.";
    byId<HTMLAnchorElement>("mobile-result").href = error instanceof PlanInputError ? `#${error.field}` : "#input-error";
    byId("mobile-result").textContent = error instanceof PlanInputError
      ? `Fix input: ${FIELDS.find(f => f.key === error.field)!.label}`
      : "Check inputs to calculate a plan";
    byId<HTMLButtonElement>("download-plan").disabled = true;
  }
}

function render(p: Plan): void {
  const { nQuestions: n, minimumDetectableEffect: mde } = p.result;
  byId("result-label").textContent = mode === "questions" ? "Questions per model" : "Detectable gap in percentage points";
  byId("result-n").textContent = mode === "questions" ? number(n) : number(mde * 100);
  const sentence = mode === "questions"
    ? `Answer the same ${number(n)} questions with each model to plan for a ${number(values.delta)}-point improvement at ${number(values.power)}% power.`
    : `With ${number(n)} shared questions, the estimated detectable gap is ${points(mde)} at ${number(values.power)}% power.`;
  byId("result-sentence").textContent = sentence;
  byId("result-status").textContent = `${sentence}${p.warnings.length ? ` ${p.warnings.join(" ")}` : ""}`;
  const warnings = byId("plan-warnings");
  warnings.replaceChildren(...p.warnings.map(warning => {
    const item = document.createElement("p");
    item.textContent = warning;
    return item;
  }));
  warnings.hidden = !p.warnings.length;
  byId("result-work").textContent = `${number(p.result.modelAnswers)} model answers in total. One answer per model per question.`;
  byId("pairing-sensitivity").textContent = mode === "questions"
    ? `If the paired correlation were 0, the same gap would need ${number(p.sensitivity.nQuestions)} questions per model. All other assumptions stay fixed.`
    : `If the paired correlation were 0, this budget's detectable gap would be ${points(p.sensitivity.minimumDetectableEffect)}. All other assumptions stay fixed.`;
  drawChart(p);
  byId("chart-caption").textContent = `The curve and marker are calculated from your assumptions. Gaps above ${points(p.result.maximumImprovement)} exceed the distance from this baseline to 100% accuracy.`;
  const rows = [...new Set([Math.max(2, Math.floor(n / 2)), n, n * 2, n * 4])];
  byId("budget-rows").replaceChildren(...rows.map(budget => {
    const row = document.createElement("tr");
    if (budget === n) row.className = "current-budget";
    const gap = minimumDetectableEffect(budget, p.inputs);
    for (const text of [number(budget) + (budget === n ? " (current)" : ""), points(gap), gap <= p.result.maximumImprovement ? "Within range" : "Exceeds 100% accuracy"]) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    }
    return row;
  }));
  const details: [string, string][] = [
    ["Variance p(1-p)", number(p.result.perQuestionVariance)],
    ["Design effect", number(p.inputs.clusterDesignEffect)],
    ["Approximate groups", number(p.result.approximateGroups)],
    ["Two-sided alpha", `${number(p.inputs.alpha * 100)}%`],
  ];
  byId("detail-strip").replaceChildren(...details.map(([label, value]) => {
    const wrap = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    wrap.append(dt, dd);
    return wrap;
  }));
  byId<HTMLTextAreaElement>("cli-command").value = p.cliCommand;
}

function drawChart(p: Plan): void {
  const container = byId("chart");
  chartWidth = Math.max(280, Math.round(container.clientWidth) || 350);
  const n = p.result.nQuestions;
  const curve = buildCurve(p.inputs, Math.max(2, Math.floor(n / 16)), Math.max(20, n * 4));
  renderChart(container, curve, {
    width: chartWidth,
    height: chartWidth < 400 ? 230 : 280,
    current: { n, mde: p.result.minimumDetectableEffect },
  });
}

buildControls();
for (const input of document.querySelectorAll<HTMLInputElement>('input[name="mode"]')) {
  input.addEventListener("change", () => {
    mode = input.value === "budget" ? "budget" : "questions";
    update();
  });
}
byId("reset-plan").addEventListener("click", () => {
  values = defaults();
  mode = "questions";
  byId<HTMLInputElement>("mode-questions").checked = true;
  for (const cfg of FIELDS) {
    byId<HTMLInputElement>(cfg.key).value = String(values[cfg.key]);
    const range = byId<HTMLInputElement>(`${cfg.key}-range`);
    if (range) {
      range.value = String(values[cfg.key]);
      range.removeAttribute("aria-valuetext");
    }
  }
  update();
  byId("action-status").textContent = "Default plan restored.";
});
byId("download-plan").addEventListener("click", () => {
  if (!currentPlan) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({ ...currentPlan, generatedAt: new Date().toISOString() }, null, 2) + "\n"], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "errorbars-plan.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
byId("select-command").addEventListener("click", () => {
  const input = byId<HTMLTextAreaElement>("cli-command");
  input.focus();
  input.select();
  byId("action-status").textContent = "Command selected. Copy it with your usual keyboard shortcut.";
});
byId("assumptions").replaceChildren(...ASSUMPTIONS.map(text => {
  const li = document.createElement("li");
  li.textContent = text;
  return li;
}));
initTheme(byId<HTMLButtonElement>("theme-toggle"));
update();

new ResizeObserver(() => {
  const width = byId("chart").clientWidth;
  if (currentPlan && width > 0 && Math.max(280, Math.round(width)) !== chartWidth) drawChart(currentPlan);
}).observe(byId("chart"));
