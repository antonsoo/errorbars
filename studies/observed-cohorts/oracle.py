"""Calculate independent paired inference on the actual native observed cohort.

Development NumPy/SciPy only; no Errorbars statistical implementation is used.
The general OLS CR2 projection is shared with the separate summary audit.
"""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, t

HERE = Path(__file__).resolve().parent
PEER = "20251205_sonar-foundation-agent_claude-opus-4-5"


def main() -> None:
    source = HERE.parent / "swe-bench-verified/data/outcomes.json"
    data = json.loads(source.read_text())
    native_path = HERE / "native/partial-details.json"
    native = json.loads(native_path.read_text())
    observed = [iid for iid in data["instances"] if iid in native]
    peer = next(s for s in data["submissions"] if s["id"] == PEER)
    bits = format(int(peer["resolved"], 16), f"0{len(data['instances'])}b")
    peer_scores = dict(zip(data["instances"], map(int, bits), strict=True))
    a = np.array([float(native[iid]["resolved"]) for iid in observed])
    b = np.array([float(peer_scores[iid]) for iid in observed])
    difference = a - b
    groups = tuple(iid.rsplit("-", 1)[0].replace("__", "/") for iid in observed)
    design = runpy.run_path(str(HERE.parent / "summary-inference/audit.py"))["design"]
    projection, dof = design(groups)
    scores = difference @ projection
    se_clustered = float(np.sqrt(scores @ scores))
    mean_diff = float(np.mean(difference))
    half_width = float(t.ppf(0.975, dof)) * se_clustered
    n01 = int(np.sum((a == 0) & (b == 1)))
    n10 = int(np.sum((a == 1) & (b == 0)))
    result = {
        "native_sha256": hashlib.sha256(native_path.read_bytes()).hexdigest(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "n": len(observed), "n_clusters": len(set(groups)),
        "resolved_a": int(a.sum()), "resolved_b": int(b.sum()),
        "mean_a": float(a.mean()), "mean_b": float(b.mean()), "mean_diff": mean_diff,
        "se_clustered": se_clustered, "dof_clustered": dof,
        "ci_low_clustered": mean_diff - half_width, "ci_high_clustered": mean_diff + half_width,
        "p_value_clustered": float(2 * t.sf(abs(mean_diff / se_clustered), dof)),
        "mcnemar": {"n01": n01, "n10": n10, "p_value": float(binomtest(n01, n01 + n10).pvalue)},
    }
    out = HERE / "results/oracle.json"
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
