import hashlib
import importlib.metadata
import json
import math
import sys
from pathlib import Path

from errorbars.adapters.inspect_ai import load_inspect_log

root = Path(sys.argv[1])
rows = []
for row in json.loads((root / "manifest.json").read_text())["observations"]:
    p = root / row["file"]
    label = p.stem.rsplit("-", 1)[0]
    profile = p.stem.rsplit("-", 1)[1]
    for selected in ["mean", "max"] if label == "mean-max" else [None]:
        for key in ["correct", "loss"] if label == "named-max" else [None]:
            d = load_inspect_log(p, score_key=key, inspect_reducer=selected)
            reducer = selected or ("max" if label == "named-max" else label)
            expected = {}
            for i in range(24):
                if profile == "concentrated":
                    value = float(i < 18)
                else:
                    value = {
                        "mean": 1 / 3,
                        "none": 1 / 3,
                        "max": 1.0,
                        "pass_at_2": 2 / 3,
                        "median": 0.0,
                        "mode": 0.0,
                        "at_least_2": 0.0,
                    }[reducer]
                if key == "loss":
                    value = (1 - value) if profile == "concentrated" else 1.0
                expected[f"q{i:02}"] = value
            values = d.scores_by_question()
            assert values.keys() == expected.keys()
            assert all(math.isclose(values[q], expected[q], abs_tol=1e-15) for q in values), (
                p,
                selected,
                key,
                values,
            )
            rows.append(
                {
                    "file": p.name,
                    "reducer": reducer,
                    "key": key,
                    "observations": len(d),
                    "questions": len(values),
                    "values": values,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
out = {
    "python": sys.version,
    "reader": importlib.metadata.version("inspect-ai"),
    "writer": json.loads((root / "manifest.json").read_text())["inspect_ai"],
    "cases": rows,
    "closed_form_checks": sum(len(r["values"]) for r in rows),
    "passed": True,
}
Path(sys.argv[2]).write_text(json.dumps(out, indent=2) + "\n")
print(
    json.dumps(
        {
            "reader": out["reader"],
            "writer": out["writer"],
            "cases": len(rows),
            "question_checks": out["closed_form_checks"],
        }
    )
)
