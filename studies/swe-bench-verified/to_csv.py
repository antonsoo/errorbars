"""Write per-task scores for chosen submissions in the CSV format the errorbars CLI reads.

    uv run python studies/swe-bench-verified/to_csv.py ID [ID ...] [--mine NAME=FILE] > scores.csv
    uv run python studies/swe-bench-verified/to_csv.py --list

ID is a submission directory name from SWE-bench/experiments, or a unique part
of one. --mine adds a run of your own: FILE is the evaluation report the
SWE-bench harness writes (a JSON object with "resolved_ids" or "resolved"), or a
text file with one resolved task id per line. Tasks it does not list count as
unresolved, as on the leaderboard.

The repository of each task goes in the cluster_id column, so errorbars also
reports the repository-level comparison. Pass --cluster-col none to the CLI to
leave it out.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _own_run(spec: str, known: set[str]) -> tuple[str, set[str]]:
    name, _, file = spec.partition("=")
    if not file:
        raise SystemExit("--mine takes NAME=FILE")
    text = Path(file).read_text(encoding="utf-8-sig")
    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        resolved = {line.strip() for line in text.splitlines() if line.strip()}
    else:
        if not isinstance(report, dict) or not ({"resolved_ids", "resolved"} & report.keys()):
            raise SystemExit(f'{file}: expected a JSON object with "resolved_ids" or "resolved"') from None
        resolved = set(report.get("resolved_ids") or report.get("resolved") or [])
    unknown = sorted(resolved - known)
    if unknown:
        raise SystemExit(
            f"{file}: {len(unknown)} ids are not SWE-bench Verified tasks (first: {unknown[0]!r})"
        )
    return name, resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("ids", nargs="*", metavar="ID")
    parser.add_argument("--mine", action="append", default=[], metavar="NAME=FILE")
    parser.add_argument("--list", action="store_true", help="print the submission ids and scores")
    parser.add_argument("--data", type=Path, default=HERE / "data" / "outcomes.json")
    args = parser.parse_args()

    data = json.loads(args.data.read_text())
    instances: list[str] = data["instances"]
    by_id = {sub["id"]: sub for sub in data["submissions"]}
    if args.list:
        for sub in sorted(data["submissions"], key=lambda s: -s["n_resolved"]):
            print(f"{100 * sub['n_resolved'] / len(instances):5.1f}  {sub['id']}")
        return

    columns: list[tuple[str, set[str]]] = []
    for wanted in args.ids:
        matches = [wanted] if wanted in by_id else [sid for sid in by_id if wanted in sid]
        if len(matches) != 1:
            hint = ", ".join(matches[:4]) if matches else "see --list"
            raise SystemExit(f"{wanted!r} names {len(matches)} submissions ({hint})")
        bits = f"{int(by_id[matches[0]]['resolved'], 16):0{len(instances)}b}"
        columns.append((matches[0], {iid for iid, bit in zip(instances, bits, strict=True) if bit == "1"}))
    columns += [_own_run(spec, set(instances)) for spec in args.mine]
    if not columns:
        parser.error("name at least one submission, or --mine NAME=FILE")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["question_id", "model", "score", "cluster_id"])
    for name, resolved in columns:
        for iid in instances:
            writer.writerow([iid, name, int(iid in resolved), iid.rsplit("-", 1)[0].replace("__", "/")])


if __name__ == "__main__":
    main()
