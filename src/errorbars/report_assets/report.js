/* The report has no runtime dependencies or network access. Imported strings
   enter the DOM through textContent; the complete evidence remains in JSON. */
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const byId = (id) => document.getElementById(id);
  const PAGE_SIZE = 40;
  const SAMPLE_PAGE_SIZE = 25;
  const CLUSTER_PAGE_SIZE = 12;
  let page = 0;
  let clusterPage = 0;
  let clusterFilter = null;
  let selected = null;
  let rows = [];
  let samplePages = { a: 0, b: 0 };

  function visible(value) {
    return String(value).replace(/[\p{Cc}\p{Cf}\p{Cs}]/gu, (character) =>
      `\\u${character.codePointAt(0).toString(16).padStart(4, "0")}`);
  }
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = visible(text);
    if (className) element.className = className;
    return element;
  }
  function button(text, action, className) {
    const element = node("button", text, className);
    element.type = "button";
    element.addEventListener("click", action);
    return element;
  }
  function number(value, signed = false) {
    if (value === null || value === undefined) return "unavailable";
    const magnitude = Math.abs(value);
    const text = magnitude > 0 && (magnitude < 0.0001 || magnitude >= 100000)
      ? value.toExponential(3) : value.toFixed(4);
    return signed && value > 0 ? `+${text}` : text;
  }
  function deltaClass(value) {
    return value > 0 ? "positive" : value < 0 ? "negative" : "";
  }
  const formatCount = (value) => value.toLocaleString("en-US");
  function svgNode(tag, attributes, text) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function chart(id, width, height, label) {
    const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": label });
    byId(id).append(svg);
    return svg;
  }

  function drawInterval() {
    byId("interval-chart").replaceChildren();
    const comp = data.comparison;
    if (!comp) return;
    const exact = data.inference?.test === "mcnemar_exact";
    const intervals = comp.se_clustered !== undefined
      ? [["Clustered", comp.ci_low_clustered, comp.ci_high_clustered], ["Unclustered", comp.ci_low, comp.ci_high]]
      : [[exact ? "t approx." : "Paired t", comp.ci_low, comp.ci_high]];
    let low = Math.min(0, ...intervals.map((row) => row[1]));
    let high = Math.max(0, ...intervals.map((row) => row[2]));
    if (low === high) { low = -1; high = 1; }
    const margin = (high - low) * 0.12;
    low -= margin; high += margin;
    const width = Math.max(280, Math.min(590, byId("interval-chart").clientWidth));
    const left = width < 420 ? 74 : 120;
    const right = width - 18;
    const x = (value) => left + (value - low) / (high - low) * (right - left);
    const height = intervals.length * 40 + 48;
    const caption = `${data.confidence * 100}% confidence intervals for A minus B, in score units`;
    const svg = chart("interval-chart", width, height,
      exact ? `${caption}. Paired-t diagnostic, not an exact McNemar interval.` : caption);
    svg.append(svgNode("line", { x1: x(0), x2: x(0), y1: 10, y2: height - 32, class: "zero-line" }));
    intervals.forEach(([name, min, max], i) => {
      const y = 28 + i * 40;
      svg.append(svgNode("text", { x: 2, y: y + 4 }, name));
      const className = i === 0 ? "ci-line" : "ci-line reference";
      svg.append(svgNode("line", { x1: x(min), x2: x(max), y1: y, y2: y, class: className }));
      for (const value of [min, max]) svg.append(svgNode("line", { x1: x(value), x2: x(value), y1: y - 6, y2: y + 6, class: className }));
      svg.append(svgNode("circle", { cx: x(comp.mean_diff), cy: y, r: i === 0 ? 5 : 3, class: "point" }));
    });
    svg.append(svgNode("line", { x1: left, x2: right, y1: height - 28, y2: height - 28, class: "axis" }));
    svg.append(svgNode("text", { x: x(0), y: 11, "text-anchor": "middle" }, "0"));
    for (const value of [low, high]) {
      svg.append(svgNode("text", { x: x(value), y: height - 7, "text-anchor": value === low ? "start" : "end" }, number(value, true)));
    }
  }

  function drawDistribution() {
    byId("difference-chart").replaceChildren();
    byId("outcome-counts").replaceChildren();
    const shared = data.questions.filter((q) => q.difference !== null);
    const a = shared.filter((q) => q.difference > 0).length;
    const b = shared.filter((q) => q.difference < 0).length;
    for (const [count, label] of [[a, "A higher"], [b, "B higher"], [shared.length - a - b, "equal"],
      [data.questions.length - shared.length, "excluded (unpaired)"]]) {
      const item = node("p");
      item.append(node("strong", formatCount(count)), node("span", label));
      byId("outcome-counts").append(item);
    }
    if (!shared.length) {
      byId("difference-chart").append(node("p", "No comparable question differences to plot.", "caption"));
      return;
    }
    let extent = 0;
    for (const q of shared) extent = Math.max(extent, Math.abs(q.difference));
    if (extent === 0) {
      byId("difference-chart").append(node("p", "Every shared question has equal average scores in A and B.", "caption"));
      return;
    }
    const counts = Array(41).fill(0);
    for (const q of shared) {
      const d = q.difference;
      const bucket = d === 0 ? 20 : d < 0 ? Math.min(19, Math.floor((d / extent + 1) * 20))
        : 21 + Math.min(19, Math.floor(d / extent * 20));
      counts[bucket] += 1;
    }
    const peak = Math.max(...counts);
    const width = Math.max(250, Math.min(1040, byId("difference-chart").clientWidth));
    const svg = chart("difference-chart", width, 150, `Distribution of ${shared.length} question differences: ${a} A higher, ${b} B higher, ${shared.length - a - b} equal. Bar height is question count.`);
    const start = width < 420 ? 32 : 65;
    const step = (width - start - 25) / 41;
    svg.append(svgNode("text", { x: 6, y: 32 }, String(peak)));
    svg.append(svgNode("text", { x: 6, y: 111 }, "0"));
    svg.append(svgNode("line", { x1: start - 5, x2: start + 41 * step, y1: 110, y2: 110, class: "axis" }));
    counts.forEach((count, i) => {
      if (!count) return;
      const height = count / peak * 80;
      const rect = svgNode("rect", { x: start + i * step, y: 110 - height, width: step * .8, height,
        class: `hist-bar ${i < 20 ? "negative" : i === 20 ? "ties" : ""}` });
      rect.append(svgNode("title", {}, `${count} questions${i === 20 ? " with equal scores" : " in this difference bin"}`));
      svg.append(rect);
    });
    for (const [i, label] of [[0, number(-extent)], [20, "0 (equal)"], [40, number(extent, true)]]) {
      svg.append(svgNode("text", { x: start + i * step + step * .4, y: 135,
        "text-anchor": i === 0 ? "start" : i === 40 ? "end" : "middle" }, label));
    }
  }

  function matches(q) {
    const search = byId("search").value.toLocaleLowerCase();
    const haystack = `${q.question_id}\n${q.cluster_id ?? ""}`.toLocaleLowerCase();
    // Search both original identifiers and their visible control-character escapes.
    if (search && !haystack.includes(search) && !visible(haystack).includes(search)) return false;
    if (clusterFilter !== null && q.cluster_id !== clusterFilter) return false;
    switch (byId("presence").value) {
      case "a_higher": return q.difference !== null && q.difference > 0;
      case "b_higher": return q.difference !== null && q.difference < 0;
      case "equal": return q.difference === 0;
      case "excluded": return q.presence !== "shared";
      case "all": return true;
      default: return q.presence === byId("presence").value;
    }
  }
  function compareQuestions(a, b) {
    const sort = byId("sort").value;
    if (sort !== "question") {
      if ((a.difference === null) !== (b.difference === null)) return a.difference === null ? 1 : -1;
      const delta = sort === "magnitude" ? Math.abs(b.difference ?? 0) - Math.abs(a.difference ?? 0)
        : sort === "ascending" ? (a.difference ?? 0) - (b.difference ?? 0) : (b.difference ?? 0) - (a.difference ?? 0);
      if (delta) return delta;
    }
    return a.question_id < b.question_id ? -1 : a.question_id > b.question_id ? 1 : 0;
  }
  function showLedger(recalculate = true) {
    if (recalculate) rows = data.questions.filter(matches).sort(compareQuestions);
    page = Math.min(page, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1));
    const fragment = document.createDocumentFragment();
    for (const q of rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)) {
      const row = node("tr", undefined, selected === q ? "selected-row" : "");
      const id = node("td");
      const opener = button(q.question_id, () => inspect(q, true), "question-link");
      opener.setAttribute("aria-label", `Inspect question ${visible(q.question_id)}`);
      opener.setAttribute("aria-controls", "inspector");
      if (selected === q) opener.setAttribute("aria-current", "true");
      id.append(opener);
      if (q.cluster_id !== null) id.append(node("span", q.cluster_id, "row-cluster"));
      row.append(id);
      for (const side of ["a", "b"]) {
        const observations = q[`observations_${side}`];
        const cell = node("td", q[`mean_${side}`] === null ? "missing" : number(q[`mean_${side}`]));
        if (observations.length > 1) cell.append(node("span", `${formatCount(observations.length)} draws`, "count-small"));
        row.append(cell);
      }
      row.append(node("td", q.difference === null ? "unpaired" : number(q.difference, true), deltaClass(q.difference)));
      const coverage = node("td");
      coverage.append(node("span", q.presence === "shared" ? "Shared" : q.presence === "only_a" ? "Only A"
        : q.presence === "conflicting" ? "Conflict" : "Only B",
        `badge ${q.presence === "shared" ? "" : "excluded"}`));
      row.append(coverage); fragment.append(row);
    }
    byId("question-rows").replaceChildren(fragment);
    byId("no-questions").hidden = rows.length > 0;
    const start = rows.length ? page * PAGE_SIZE + 1 : 0;
    byId("row-status").textContent = `Showing ${formatCount(start)}-${formatCount(Math.min(rows.length, (page + 1) * PAGE_SIZE))} of ${formatCount(rows.length)} matching questions (${formatCount(data.questions.length)} total).`;
    byId("page-number").textContent = rows.length ? `Page ${page + 1} of ${Math.ceil(rows.length / PAGE_SIZE)}` : "No matching rows";
    byId("previous").disabled = page === 0;
    byId("next").disabled = (page + 1) * PAGE_SIZE >= rows.length;
    byId("download-csv").disabled = rows.length === 0;
    byId("cluster-filter").hidden = clusterFilter === null;
    if (clusterFilter !== null) {
      byId("cluster-filter").replaceChildren(node("span", `Cluster: ${clusterFilter} `), button("Clear cluster filter", () => {
        clusterFilter = null; changeFilters(); byId("search").focus();
      }));
    }
  }

  function clearInspector() {
    selected = null;
    const heading = node("h3", "Select a question");
    heading.id = "inspector-heading"; heading.tabIndex = -1;
    byId("inspector").replaceChildren(heading, node("p", "Open a question id to see every observed generation and its source record.", "caption"));
  }
  function changeFilters() {
    page = 0; clearInspector(); showLedger();
  }
  function returnToQuestion(q) {
    const position = rows.indexOf(q);
    if (position >= 0) {
      page = Math.floor(position / PAGE_SIZE); showLedger(false);
      const opener = byId("question-rows").querySelectorAll(".question-link")[position % PAGE_SIZE];
      opener.focus();
    } else byId("search").focus();
  }
  function sourceText(observation) {
    if (observation.source === null) return "Source location unavailable";
    const source = data.sources[observation.source];
    let label = `[${source.id + 1}] ${source.name} / record ${observation.record}`;
    if (observation.line_start !== null) {
      label += observation.line_start === observation.line_end ? ` / line ${observation.line_start}`
        : ` / lines ${observation.line_start}-${observation.line_end}`;
    }
    return label;
  }
  function inspect(q, focus = false, resetSamples = true) {
    if (resetSamples) samplePages = { a: 0, b: 0 };
    selected = q;
    const root = byId("inspector");
    const heading = node("h3", q.question_id);
    heading.id = "inspector-heading"; heading.tabIndex = -1;
    root.replaceChildren(button("Back to question", () => returnToQuestion(q), "close-inspector interactive"),
      node("p", "Selected question", "eyebrow"), heading);
    if (q.cluster_id !== null) root.append(node("p", `Cluster: ${q.cluster_id}`, "caption"));
    root.append(node("p", q.identity === "conflicting"
      ? "Conflicting question content: this id has different known signatures. The paired result is withheld for the entire comparison."
      : q.scoring === "conflicting"
      ? "Conflicting scoring rules: the recorded scorer names or configurations differ. Re-score both runs under the same rule before comparing."
      : q.difference === null ? "Excluded from the paired estimate: one model has no observed score. Missing is not zero."
      : `A - B = ${number(q.difference, true)}. Each model's score is the mean of its observed draws.`, "caption"));
    root.append(node("p", `Question identity: ${q.identity}.`, "caption"));
    root.append(node("p", `Scoring declarations: ${q.scoring ?? "unavailable"}.`, "caption"));
    for (const side of ["a", "b"]) {
      const observations = q[`observations_${side}`];
      root.append(node("h4", `${side.toUpperCase()} / ${data[`model_${side}`]}`));
      if (!observations.length) {
        root.append(node("p", "No observation in these inputs.", "caption")); continue;
      }
      root.append(node("p", `Mean ${number(q[`mean_${side}`])} / ${formatCount(observations.length)} observation${observations.length === 1 ? "" : "s"}`, "caption"));
      const scroll = node("div", undefined, "table-scroll");
      scroll.tabIndex = 0; scroll.setAttribute("role", "region");
      scroll.setAttribute("aria-label", `${side.toUpperCase()} observed generations`);
      const table = node("table");
      table.append(node("caption", `Observed scores for ${side.toUpperCase()}`, "sr-only"));
      const head = node("thead"); const header = node("tr");
      for (const label of ["Sample", "Score", "Source record"]) {
        const th = node("th", label); th.scope = "col"; header.append(th);
      }
      head.append(header); table.append(head);
      const body = node("tbody");
      const offset = samplePages[side] * SAMPLE_PAGE_SIZE;
      for (const obs of observations.slice(offset, offset + SAMPLE_PAGE_SIZE)) {
        const row = node("tr");
        const sample = node("td", obs.sample ?? "not set", "sample-cell");
        const source = node("td", sourceText(obs), "source-cell");
        if (obs.metric !== null) source.append(node("span", `Score: ${obs.metric}`, "source-meta"));
        if (obs.filter !== null) source.append(node("span", `Filter: ${obs.filter}`, "source-meta"));
        if (obs.scorer) source.append(node("span", `Scorer: ${obs.scorer}`, "source-meta"));
        if (obs.scorer_config) {
          const proof = node("details"); proof.append(node("summary", "Scorer configuration fingerprint"));
          proof.append(node("p", obs.scorer_config, "caption")); source.append(proof);
        }
        if (obs.question_hash !== null) {
          const proof = node("details"); proof.append(node("summary", "Question signature"));
          proof.append(node("p", obs.question_hash, "caption")); source.append(proof);
        }
        row.append(sample, node("td", String(obs.score)), source); body.append(row);
      }
      table.append(body); scroll.append(table); root.append(scroll);
      const pager = node("div", undefined, "inspect-pages interactive");
      const previous = button(`Previous ${side.toUpperCase()} draws`, () => {
        samplePages[side]--; inspect(q, false, false); byId(`draws-${side}`).focus();
      });
      previous.disabled = offset === 0;
      const next = button(`Next ${side.toUpperCase()} draws`, () => {
        samplePages[side]++; inspect(q, false, false); byId(`draws-${side}`).focus();
      });
      next.disabled = offset + SAMPLE_PAGE_SIZE >= observations.length;
      const status = node("span", `${offset + 1}-${Math.min(offset + SAMPLE_PAGE_SIZE, observations.length)} of ${observations.length} draws`);
      status.id = `draws-${side}`; status.tabIndex = -1;
      pager.append(previous, status, next);
      if (observations.length > SAMPLE_PAGE_SIZE) root.append(pager);
    }
    showLedger(false);
    if (focus) heading.focus();
  }

  function showClusters() {
    if (!data.clusters.length) return;
    byId("cluster-section").hidden = false;
    const body = byId("cluster-rows"); body.replaceChildren();
    for (const c of data.clusters.slice(clusterPage * CLUSTER_PAGE_SIZE, (clusterPage + 1) * CLUSTER_PAGE_SIZE)) {
      const row = node("tr"); const label = node("td");
      label.append(button(c.cluster_id, () => {
        clusterFilter = c.cluster_id; byId("search").value = ""; byId("presence").value = "shared";
        changeFilters(); byId("questions").focus();
      }, "cluster-link"));
      row.append(label, node("td", formatCount(c.n)), node("td", number(c.mean_difference, true)),
        node("td", number(c.without_difference, true), deltaClass(c.without_difference)),
        node("td", number(c.shift, true)));
      body.append(row);
    }
    byId("cluster-status").textContent = `Page ${clusterPage + 1} of ${Math.ceil(data.clusters.length / CLUSTER_PAGE_SIZE)} / ${formatCount(data.clusters.length)} clusters, largest shifts first`;
    byId("cluster-previous").disabled = clusterPage === 0;
    byId("cluster-next").disabled = (clusterPage + 1) * CLUSTER_PAGE_SIZE >= data.clusters.length;
  }

  function download(content, mime, filename) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const anchor = node("a"); anchor.href = url; anchor.download = filename;
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function csvCell(value) {
    if (value === null) return '""';
    let text = String(value);
    if (typeof value === "string" && /^[\s\p{Cf}]*[=+@\-\t\r\n]/u.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  }
  byId("download-json").addEventListener("click", () => {
    download(JSON.stringify(data, null, 2) + "\n", "application/json;charset=utf-8", "errorbars-comparison.json");
  });
  byId("download-csv").addEventListener("click", () => {
    const header = ["question_id", "cluster_id", "presence", "identity", "scoring", "model_a", "model_b", "mean_a", "mean_b",
      "difference_a_minus_b", "n_observations_a", "n_observations_b"];
    const lines = [header.map(csvCell).join(",")];
    for (const q of rows) lines.push([q.question_id, q.cluster_id, q.presence, q.identity, q.scoring, data.model_a, data.model_b,
      q.mean_a, q.mean_b, q.difference, q.observations_a.length, q.observations_b.length].map(csvCell).join(","));
    download(lines.join("\r\n") + "\r\n", "text/csv;charset=utf-8", "errorbars-questions.csv");
  });
  byId("search").addEventListener("input", changeFilters);
  byId("presence").addEventListener("change", changeFilters);
  byId("sort").addEventListener("change", changeFilters);
  byId("reset-filters").addEventListener("click", () => {
    byId("search").value = ""; byId("presence").value = "all"; byId("sort").value = "magnitude";
    clusterFilter = null; changeFilters();
  });
  byId("previous").addEventListener("click", () => { page--; showLedger(false); byId("questions").focus(); });
  byId("next").addEventListener("click", () => { page++; showLedger(false); byId("questions").focus(); });
  byId("cluster-previous").addEventListener("click", () => { clusterPage--; showClusters(); });
  byId("cluster-next").addEventListener("click", () => { clusterPage++; showClusters(); });
  for (const [id, filter] of [["show-shared", "shared"], ["show-missing", "excluded"]]) {
    byId(id).addEventListener("click", () => {
      byId("search").value = ""; byId("presence").value = filter; clusterFilter = null;
      changeFilters(); byId("questions").focus();
    });
  }
  const darkPreference = matchMedia("(prefers-color-scheme: dark)");
  function updateThemeLabel() {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark" : darkPreference.matches;
    byId("theme").textContent = dark ? "Light theme" : "Dark theme";
    byId("theme").setAttribute("aria-label", dark ? "Use light theme" : "Use dark theme");
  }
  byId("theme").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark" : darkPreference.matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark"; updateThemeLabel();
  });
  darkPreference.addEventListener("change", updateThemeLabel);
  let resizeFrame;
  window.addEventListener("resize", () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => { drawInterval(); drawDistribution(); });
  });
  updateThemeLabel(); drawInterval(); drawDistribution(); showLedger(); showClusters();
  if (rows.length) inspect(rows[0]);
})();
