"""A self-contained, offline HTML artifact for a paired comparison review."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import tempfile
import unicodedata
from importlib.resources import files
from pathlib import Path
from string import Template

from errorbars import __version__
from errorbars.review import ComparisonReview

__all__ = ["comparison_html", "write_comparison_html"]


def _text(value: object) -> str:
    # Rendering a control/bidi character verbatim can hide part of an identifier.
    # The JSON still contains the original value for lossless evidence export.
    visible = "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cc", "Cf", "Cs") else c for c in str(value)
    )
    return html.escape(visible)


def _number(value: float | int | None, signed: bool = False) -> str:
    if value is None:
        return "unavailable"
    if value and (abs(value) < 0.0001 or abs(value) >= 100000):
        return f"{value:+.3e}" if signed else f"{value:.3e}"
    return f"{value:+.4f}" if signed else f"{value:.4f}"


def _hash(content: str) -> str:
    return base64.b64encode(hashlib.sha256(content.encode("utf-8")).digest()).decode("ascii")


def comparison_html(review: ComparisonReview) -> str:
    """Render the entire evidence artifact, including fonts and source records.

    Basenames identify files without exposing full local paths. Model, question,
    sample and cluster labels are included. No prompts or completions are stored.
    Scripts and styles are allowed only by their exact CSP hashes; all network
    access is denied. There are no sidecar files or third-party runtime scripts.
    """
    assets = files("errorbars").joinpath("report_assets")
    css = assets.joinpath("report.css").read_text(encoding="utf-8")
    for family, name, weight in [
        ("Spectral", "spectral-500-latin.woff2", "500"),
        ("IBM Plex Sans", "ibm-plex-sans-latin.woff2", "100 900"),
        ("IBM Plex Mono", "ibm-plex-mono-400-latin.woff2", "400"),
    ]:
        encoded = base64.b64encode(assets.joinpath("fonts", name).read_bytes()).decode("ascii")
        css += (
            f'\n@font-face {{ font-family: "{family}"; font-style: normal; font-weight: {weight}; '
            f'font-display: swap; src: url(data:font/woff2;base64,{encoded}) format("woff2"); }}\n'
        )
    license_text = assets.joinpath("fonts", "LICENSE.txt").read_text(encoding="utf-8")
    css += "\n/* Embedded font licenses:\n" + license_text.replace("*/", "* /") + "\n*/\n"
    script = assets.joinpath("report.js").read_text(encoding="utf-8")
    csp = (
        f"default-src 'none'; script-src 'sha256-{_hash(script)}'; "
        f"style-src 'sha256-{_hash(css)}'; font-src data:; img-src data:; "
        "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    c = review.cohort
    comp = review.comparison
    interval_table = ""
    if comp is None:
        inference = (
            f"Inference unavailable: {_text(review.unavailable_reason)}. Observed scores remain below."
        )
    else:
        clustered = comp.se_clustered is not None
        lo, hi = (comp.ci_low_clustered, comp.ci_high_clustered) if clustered else (comp.ci_low, comp.ci_high)
        p = comp.p_value_clustered if clustered else comp.p_value
        inference = (
            f"{review.confidence * 100:g}% {'cluster-robust ' if clustered else 'paired '}CI "
            f"[{_number(lo)}, {_number(hi)}]; two-sided p = {_number(p)}."
        )
        if lo is not None and hi is not None and lo <= 0 <= hi:
            inference += " The interval includes zero; it does not establish a difference or equivalence."
        if clustered:
            inference += f" Based on {c['n_clusters']} independent clusters."
        rows: list[tuple[str, float | None, float | None, float | None]] = [
            ("Paired (unclustered)", comp.ci_low, comp.ci_high, comp.p_value)
        ]
        if clustered:
            rows.insert(0, ("Cluster-robust (primary)", comp.ci_low_clustered,
                            comp.ci_high_clustered, comp.p_value_clustered))
        interval_table = (
            '<table class="interval-table"><caption class="sr-only">Confidence intervals and tests</caption>'
            '<thead><tr><th scope="col">Method</th><th scope="col">'
            f'{review.confidence * 100:g}% interval</th><th scope="col">p-value</th></tr></thead><tbody>'
            + "".join(
                f"<tr><td>{name}</td><td>[{_number(low)}, {_number(high)}]</td><td>{_number(pv)}</td></tr>"
                for name, low, high, pv in rows
            ) + "</tbody></table>"
        )
        if comp.mcnemar is not None:
            suffix = " Unadjusted for clustering." if clustered else ""
            interval_table += (
                '<p class="caption">Exact McNemar (binary question scores): '
                f"p = {_number(comp.mcnemar.p_value)}.{suffix}</p>"
            )
    cohort_rows = []
    for label, a, b in [
        ("Questions in these inputs", c["n_a"], c["n_b"]),
        ("Shared question ids", c["n_shared"], c["n_shared"]),
        ("Only in this run / excluded", c["n_only_a"], c["n_only_b"]),
        ("Observations in these inputs", c["n_observations_a"], c["n_observations_b"]),
        ("Observations on shared questions", c["n_shared_observations_a"], c["n_shared_observations_b"]),
        ("Mean on all questions", _number(c["mean_all_a"]), _number(c["mean_all_b"])),
        ("Mean on shared questions", _number(c["mean_shared_a"]), _number(c["mean_shared_b"])),
    ]:
        cohort_rows.append(f"<tr><td>{label}</td><td>{a}</td><td>{b}</td></tr>")
    coverage_note = (
        "The runs cover different questions. Comparing the all-question means mixes performance "
        "with a change in the question set. The estimate uses only the shared cohort."
        if c["n_only_a"] or c["n_only_b"] else
        "Both runs cover the same observed question ids. "
        "Questions missing from both inputs cannot be detected."
    )
    identity_note = (
        f"Question identity: {c['n_identity_matching']} matching, "
        f"{c['n_identity_partial']} partially checked, "
        f"{c['n_identity_unavailable']} unchecked, {c['n_identity_conflicting']} conflicting shared ids. "
        "Matching signatures check supplied question content, not scoring-rule equivalence."
    )
    payload = json.dumps(review.as_dict(), ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    # JSON is inert script data, but the HTML parser still recognizes </script>.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Template(assets.joinpath("template.html").read_text(encoding="utf-8")).substitute(
        csp=html.escape(csp, quote=True), css=css, script=script, data=payload,
        title=f"errorbars: {_text(review.model_a)} vs {_text(review.model_b)}",
        model_a=_text(review.model_a), model_b=_text(review.model_b),
        n_shared=c["n_shared"], effect=_number(c["mean_difference"], signed=True),
        inference=inference, interval_table=interval_table, cohort_rows="".join(cohort_rows),
        coverage_note=coverage_note, warnings="".join(f"<li>{_text(w)}</li>" for w in review.warnings),
        identity_note=identity_note,
        sources="".join(f"<li>{_text(name)}</li>" for name in review.sources)
        or "<li>Source locations were not provided.</li>", version=_text(__version__),
    )


def write_comparison_html(review: ComparisonReview, path: str | Path) -> None:
    """Write atomically; a failed replacement leaves the previous report intact."""
    destination = Path(path)
    content = comparison_html(review)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", prefix=f".{destination.name}.",
            suffix=".tmp", dir=destination.parent, delete=False,
        ) as f:
            temporary = f.name
            f.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
